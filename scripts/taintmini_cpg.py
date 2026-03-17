#!/usr/bin/env python3
"""Analyze an exported CPG JSON with a TaintMini-like post-processing flow."""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def filter_results(results, config):
    if ("sources" not in config or len(config["sources"]) == 0) and (
        "sinks" not in config or len(config["sinks"]) == 0
    ):
        return results

    filtered = {}
    sources = config.get("sources", [])
    sinks = config.get("sinks", [])

    for page in results:
        filtered[page] = []
        for flow in results[page]:
            source_ok = True
            sink_ok = True

            if len(sources) > 0:
                source_ok = flow["source"] in sources
                if "[double_binding]" in sources and flow["source"].startswith("[data from double binding:"):
                    source_ok = True

            if len(sinks) > 0:
                sink_ok = flow["sink"] in sinks

            if source_ok and sink_ok:
                filtered[page].append(flow)

        if len(filtered[page]) == 0:
            filtered.pop(page)

    return filtered


def load_cpg(cpg_path):
    with open(cpg_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError("invalid cpg json")

    return nodes, edges


def node_labels(node):
    labels = node.get("labels", [])
    return labels if isinstance(labels, list) else []


def node_properties(node):
    properties = node.get("properties", {})
    return properties if isinstance(properties, dict) else {}


def node_line(node):
    line = node_properties(node).get("startLine")
    return line if isinstance(line, int) else -1


def node_column(node):
    column = node_properties(node).get("startColumn")
    return column if isinstance(column, int) else -1


def node_file(node):
    artifact = node_properties(node).get("artifact", "")
    if not isinstance(artifact, str):
        return ""
    if artifact.startswith("file:"):
        return artifact[5:]
    return artifact


def normalize_text(value):
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def node_text(node):
    props = node_properties(node)
    for key in ("code", "localName", "name", "fullName"):
        value = props.get(key)
        if isinstance(value, str) and value:
            return normalize_text(value)
    return ""


def method_name(node):
    props = node_properties(node)
    local_name = props.get("localName")
    if isinstance(local_name, str) and local_name:
        return local_name

    name = props.get("name")
    if isinstance(name, str) and name:
        return name.split(".")[-1]

    full_name = props.get("fullName")
    if isinstance(full_name, str) and full_name:
        return full_name.split(".")[-1]

    return None


def build_edge_index(edges):
    forward = defaultdict(lambda: defaultdict(list))
    reverse = defaultdict(lambda: defaultdict(list))

    for edge in edges:
        edge_type = edge.get("type")
        start = edge.get("startNode")
        end = edge.get("endNode")
        if not isinstance(edge_type, str) or not isinstance(start, int) or not isinstance(end, int):
            continue

        forward[edge_type][start].append(end)
        reverse[edge_type][end].append(start)

    return forward, reverse


def artifact_to_page_name(artifact):
    if not artifact:
        return "<unknown>"

    path = Path(artifact)
    parts = path.parts
    if "pages" in parts:
        page_root = parts.index("pages") + 1
        return Path(*parts[page_root:]).with_suffix("").as_posix()

    return path.stem or path.name


def sort_graph_nodes(nodes):
    return sorted(nodes, key=lambda node: (node_line(node), node_column(node), node.get("id", -1)))


def collect_functions(nodes_by_id):
    functions = []
    for node_id, node in nodes_by_id.items():
        if "Function" not in node_labels(node):
            continue

        artifact = node_file(node)
        if not artifact:
            continue

        functions.append(
            {
                "id": node_id,
                "page_name": artifact_to_page_name(artifact),
                "artifact": artifact,
                "start_line": node_line(node),
                "end_line": node_properties(node).get("endLine", node_line(node)),
                "method_name": method_name(node),
            }
        )

    return sorted(functions, key=lambda fn: (fn["artifact"], fn["start_line"], fn["id"]))


def collect_references(nodes_by_id):
    references_by_file = defaultdict(list)
    for node in nodes_by_id.values():
        labels = set(node_labels(node))
        if "Reference" not in labels or "MemberAccess" in labels:
            continue

        artifact = node_file(node)
        if artifact:
            references_by_file[artifact].append(node)

    for artifact in references_by_file:
        references_by_file[artifact] = sort_graph_nodes(references_by_file[artifact])

    return references_by_file


def function_contains_line(function, line):
    if line < 0:
        return False

    start_line = function["start_line"]
    end_line = function["end_line"]
    if not isinstance(start_line, int) or not isinstance(end_line, int):
        return False

    return start_line <= line <= end_line


def function_span(function):
    start_line = function["start_line"]
    end_line = function["end_line"]
    if not isinstance(start_line, int) or not isinstance(end_line, int):
        return float("inf")

    return max(end_line - start_line, 0)


def display_method_name(function):
    return function["method_name"] if function["method_name"] else "<unknown>"


def select_owner_function(functions, line):
    containing = [function for function in functions if function_contains_line(function, line)]
    if len(containing) == 0:
        return None

    named = [function for function in containing if function["method_name"]]
    candidates = named if len(named) > 0 else containing
    return min(
        candidates,
        key=lambda function: (function_span(function), -function["start_line"], function["id"]),
    )


def nearest_call_expr_node(node_id, nodes_by_id, reverse_ast):
    queue = deque([node_id])
    visited = set()

    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)

        current_node = nodes_by_id.get(current)
        if current_node is None:
            continue

        if "Call" in node_labels(current_node):
            return current

        for parent in reverse_ast.get(current, []):
            queue.append(parent)

    return None


def obtain_callee_from_call_expr(call_id, nodes_by_id):
    if call_id is None:
        return None

    call_node = nodes_by_id.get(call_id)
    if call_node is None:
        return None

    props = node_properties(call_node)
    for key in ("fullName", "name", "code"):
        value = props.get(key)
        if isinstance(value, str) and value:
            return value

    return None


def find_argument_root(node_id, call_id, reverse_ast, arguments_for_call):
    queue = deque([node_id])
    visited = set()
    argument_roots = set(arguments_for_call.get(call_id, []))

    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)

        if current in argument_roots:
            return current

        if current == call_id:
            continue

        for parent in reverse_ast.get(current, []):
            queue.append(parent)

    return None


def is_page_method_parameter(node):
    return "Parameter" in node_labels(node)


def get_initializer(node_id, nodes_by_id, forward_edges):
    labels = set(node_labels(nodes_by_id[node_id]))

    candidates = []
    if "Reference" in labels:
        candidates.extend(forward_edges["REFERS_TO"].get(node_id, []))
    candidates.append(node_id)

    for candidate_id in candidates:
        for initializer_id in forward_edges["INITIALIZER"].get(candidate_id, []):
            return initializer_id, candidate_id

    return None, None


def expression_text(node_id, nodes_by_id):
    node = nodes_by_id.get(node_id)
    if node is None:
        return None

    text = node_text(node)
    return text if text else None


def check_immediate_data_dep_parent(node_id, nodes_by_id, forward_edges, reverse_ast):
    labels = set(node_labels(nodes_by_id[node_id]))

    if "Call" in labels:
        return obtain_callee_from_call_expr(node_id, nodes_by_id)

    initializer_id, owner_id = get_initializer(node_id, nodes_by_id, forward_edges)
    if initializer_id is not None:
        call_id = nearest_call_expr_node(initializer_id, nodes_by_id, reverse_ast)
        source = obtain_callee_from_call_expr(call_id, nodes_by_id)
        if source is not None:
            return source

        source = expression_text(initializer_id, nodes_by_id)
        if source is not None:
            return source

        source = expression_text(owner_id, nodes_by_id)
        if source is not None:
            return source

    return None


def handle_page_method_parameter(node_id, nodes_by_id):
    value = node_text(nodes_by_id[node_id])
    if value:
        return {f"[data from page parameter: {value}]"}
    return {"[data from page parameter: <unknown>]"}


def provenance_like_parents(node_id, forward_edges, reverse_dfg):
    queue = deque([node_id])
    visited = set()
    results = []

    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)

        for parent in reverse_dfg.get(current, []):
            if parent not in visited:
                results.append(parent)
                queue.append(parent)

        for target in forward_edges["REFERS_TO"].get(current, []):
            if target not in visited:
                results.append(target)
                queue.append(target)

        for initializer in forward_edges["INITIALIZER"].get(current, []):
            if initializer not in visited:
                results.append(initializer)
                queue.append(initializer)

    return results


def handle_data_dep_parents(node_id, nodes_by_id, forward_edges, reverse_ast, reverse_dfg):
    source = check_immediate_data_dep_parent(node_id, nodes_by_id, forward_edges, reverse_ast)
    if source is not None:
        return {source}

    source = obtain_callee_from_call_expr(
        nearest_call_expr_node(node_id, nodes_by_id, reverse_ast), nodes_by_id
    )
    if source is not None and source != "":
        return {source}

    sources = set()
    for parent_id in provenance_like_parents(node_id, forward_edges, reverse_dfg):
        parent_node = nodes_by_id[parent_id]
        if is_page_method_parameter(parent_node):
            sources.update(handle_page_method_parameter(parent_id, nodes_by_id))
            continue

        source = check_immediate_data_dep_parent(parent_id, nodes_by_id, forward_edges, reverse_ast)
        if source is None:
            source = obtain_callee_from_call_expr(
                nearest_call_expr_node(parent_id, nodes_by_id, reverse_ast), nodes_by_id
            )

        if source is not None and source != "":
            sources.add(source)

    return sources


def is_sink_identifier(node_id, call_id, forward_edges, reverse_dfg, reverse_ast):
    if len(reverse_dfg.get(node_id, [])) == 0:
        return False

    argument_root = find_argument_root(node_id, call_id, reverse_ast, forward_edges["ARGUMENTS"])
    return argument_root is not None


def handle_identifier_node(node_id, method_name_value, flows, seen_flows, nodes_by_id, forward_edges, reverse_edges):
    reverse_dfg = reverse_edges["DFG"]
    reverse_ast = reverse_edges["AST"]

    call_id = nearest_call_expr_node(node_id, nodes_by_id, reverse_ast)
    if call_id is None:
        return

    if not is_sink_identifier(node_id, call_id, forward_edges, reverse_dfg, reverse_ast):
        return

    sink = obtain_callee_from_call_expr(call_id, nodes_by_id)
    if sink is None or sink == "":
        return

    sources = set()
    for parent_id in reverse_dfg.get(node_id, []):
        sources.update(
            handle_data_dep_parents(parent_id, nodes_by_id, forward_edges, reverse_ast, reverse_dfg)
        )

    if len(sources) == 0:
        return

    ident = node_text(nodes_by_id[node_id]) or "<unknown>"
    for source in sorted(sources):
        flow = (method_name_value, ident, source, sink)
        if flow in seen_flows:
            continue
        seen_flows.add(flow)
        flows.append(
            {
                "method": method_name_value,
                "ident": ident,
                "source": source,
                "sink": sink,
            }
        )


def analyze_page_worker(page_name, functions, references_by_file, nodes_by_id, forward_edges, reverse_edges):
    page_results = []
    seen_flows = set()

    functions_by_artifact = defaultdict(list)
    for function in functions:
        functions_by_artifact[function["artifact"]].append(function)

    for artifact, artifact_functions in functions_by_artifact.items():
        refs = references_by_file.get(artifact, [])
        for node in refs:
            line = node_line(node)
            function = select_owner_function(artifact_functions, line)
            if function is None:
                continue

            handle_identifier_node(
                node.get("id"),
                display_method_name(function),
                page_results,
                seen_flows,
                nodes_by_id,
                forward_edges,
                reverse_edges,
            )

    return {page_name: page_results}


def retrieve_pages_from_cpg(functions):
    pages = defaultdict(list)
    for function in functions:
        pages[function["page_name"]].append(function)
    return dict(pages)


def write_results(result_path, results):
    with open(result_path, "w", encoding="utf-8") as handle:
        handle.write("page_name | page_method | ident | source | sink\n")
        for page in sorted(results):
            for flow in results[page]:
                handle.write(
                    f"{page} | {flow['method']} | {flow['ident']} | {flow['source']} | {flow['sink']}\n"
                )


def write_bench(bench_path, workers):
    with open(bench_path, "w", encoding="utf-8") as handle:
        handle.write("page|start|end\n")
        for page in sorted(workers):
            handle.write(f"{page}|{workers[page]['begin_time']}|{workers[page]['end_time']}\n")


def analyze_cpg_graph(cpg_path, results_path, config, workers, bench):
    if not os.path.exists(cpg_path):
        print("[main] invalid input path")
        return

    nodes, edges = load_cpg(cpg_path)
    nodes_by_id = {}
    for node in nodes:
        node_id = node.get("id")
        if isinstance(node_id, int):
            nodes_by_id[node_id] = node

    functions = collect_functions(nodes_by_id)
    pages = retrieve_pages_from_cpg(functions)
    if len(pages) == 0:
        print("[main] no page found")
        return

    if not os.path.exists(results_path):
        os.mkdir(results_path)
    elif os.path.isfile(results_path):
        print("[main] error: invalid output path")
        return

    forward_edges, reverse_edges = build_edge_index(edges)
    references_by_file = collect_references(nodes_by_id)

    max_workers = workers if workers is not None else os.cpu_count() or 1
    page_jobs = {}
    all_results = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for page_name, page_functions in pages.items():
            page_jobs[page_name] = {
                "future": executor.submit(
                    analyze_page_worker,
                    page_name,
                    page_functions,
                    references_by_file,
                    nodes_by_id,
                    forward_edges,
                    reverse_edges,
                )
            }
            if bench:
                page_jobs[page_name]["begin_time"] = int(time.time())

        for page_name in sorted(page_jobs):
            try:
                result = page_jobs[page_name]["future"].result()
                all_results.update(result)
            except Exception as error:
                print(f"[main] critical error: {error}")
            finally:
                if bench:
                    page_jobs[page_name]["end_time"] = int(time.time())

    filtered = filter_results(all_results, config)
    base_name = Path(cpg_path).stem
    write_results(os.path.join(results_path, f"{base_name}-result.csv"), filtered)

    if bench:
        write_bench(os.path.join(results_path, f"{base_name}-bench.csv"), page_jobs)


def is_cpg_json_file(path):
    if not path.lower().endswith(".json"):
        return False

    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return False

    return isinstance(data, dict) and isinstance(data.get("nodes"), list) and isinstance(
        data.get("edges"), list
    )


def iter_inputs(input_path):
    if os.path.isfile(input_path) and is_cpg_json_file(input_path):
        yield input_path
        return

    with open(input_path, "r", encoding="utf-8") as handle:
        for line in handle:
            item = line.strip()
            if item:
                yield item


def parse_args():
    parser = argparse.ArgumentParser(
        prog="taint-mini-cpg", formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "-i",
        "--input",
        dest="input",
        metavar="path",
        type=str,
        required=True,
        help="path of input cpg json(s). Single cpg json file or index files will both be fine.",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output",
        metavar="path",
        type=str,
        default="results",
        help="path of output results. The output file will be stored outside of the cpg json files.",
    )
    parser.add_argument(
        "-c",
        "--config",
        dest="config",
        metavar="path",
        type=str,
        help="path of config file. See default config file for example. Leave the field empty to include all results.",
    )
    parser.add_argument(
        "-j", "--jobs", dest="workers", metavar="number", type=int, default=None, help="number of workers."
    )
    parser.add_argument(
        "-b",
        "--bench",
        dest="bench",
        action="store_true",
        help="enable benchmark data log. Default: False",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    input_path = args.input
    output_path = args.output
    config_path = args.config
    workers = args.workers
    bench = args.bench

    if config_path is None:
        config = {}
    else:
        try:
            with open(config_path, "r", encoding="utf-8") as handle:
                config = json.load(handle)
        except FileNotFoundError:
            print("[main] error: config not found")
            return

    if not os.path.exists(input_path):
        print("[main] error: invalid input path")
        return

    if os.path.isfile(input_path):
        try:
            for item in iter_inputs(input_path):
                analyze_cpg_graph(item, output_path, config, workers, bench)
        except FileNotFoundError:
            print("[main] error: invalid input path")
        return

    print("[main] error: invalid input path")


if __name__ == "__main__":
    main()
