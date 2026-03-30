/*
 * Copyright (c) 2026, Fraunhofer AISEC. All rights reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 *                    $$$$$$\  $$$$$$$\   $$$$$$\
 *                   $$  __$$\ $$  __$$\ $$  __$$\
 *                   $$ /  \__|$$ |  $$ |$$ /  \__|
 *                   $$ |      $$$$$$$  |$$ |$$$$\
 *                   $$ |      $$  ____/ $$ |\_$$ |
 *                   $$ |  $$\ $$ |      $$ |  $$ |
 *                   \$$$$$   |$$ |      \$$$$$   |
 *                    \______/ \__|       \______/
 *
 */
package de.fraunhofer.aisec.cpg.frontends.typescript

import de.fraunhofer.aisec.cpg.graph.*
import de.fraunhofer.aisec.cpg.graph.declarations.Field
import de.fraunhofer.aisec.cpg.graph.declarations.Method
import de.fraunhofer.aisec.cpg.graph.declarations.Parameter
import de.fraunhofer.aisec.cpg.graph.declarations.Record
import de.fraunhofer.aisec.cpg.graph.declarations.TranslationUnit
import de.fraunhofer.aisec.cpg.graph.types.Type

/**
 * Best-effort lowering for ArkUI page files.
 *
 * The TypeScript parser already exposes most ArkUI page bodies as AST nodes, but the top-level
 * declarations are shaped differently from standard TypeScript classes and methods. This adapter
 * reconstructs a record with fields and methods from the SourceFile children so the regular CPG
 * passes can still build call and data-flow edges.
 */
class ArkUiAdapter(private val frontend: TypeScriptLanguageFrontend) {
    companion object {
        private val structNameRegex = Regex("""\bstruct\s+([A-Za-z_][A-Za-z0-9_]*)\b""")
        private val typedNameRegex =
            Regex("""^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([^=;]+?)(?:\s*=.*)?;?\s*$""")
    }

    fun handleSourceFile(node: TypeScriptNode): TranslationUnit? {
        val sourceCode = frontend.codeOf(node) ?: return null
        val componentName =
            structNameRegex.find(sourceCode)?.groupValues?.getOrNull(1) ?: return null

        val translationUnit =
            with(frontend) { newTranslationUnit(node.location.file, rawNode = node) }
        frontend.scopeManager.resetToGlobal(translationUnit)

        val record = frontend.newRecord(componentName, "struct", rawNode = node)
        frontend.scopeManager.addDeclaration(record)
        translationUnit.declarations += record

        node.children
            ?.firstOrNull {
                isDecoratorCarrier(it) &&
                    (hasDecorator(it, "Entry") || hasDecorator(it, "Component"))
            }
            ?.let { frontend.processAnnotations(record, it) }

        frontend.scopeManager.enterScope(record)

        val children = node.firstChild("Block")?.children ?: emptyList()
        var pendingDecorators: TypeScriptNode? = null
        var index = 0

        while (index < children.size) {
            val child = children[index]
            val nextChild = children.getOrNull(index + 1)

            if (isDecoratorCarrier(child)) {
                pendingDecorators = child
                index++
                continue
            }

            if (isArkUiCallbackField(child, nextChild)) {
                createCallbackMethod(record, child, nextChild!!, pendingDecorators)?.let {
                    frontend.scopeManager.addDeclaration(it)
                    record.addDeclaration(it)
                }
                pendingDecorators = null
                index += 2
                continue
            }

            if (isArkUiField(child)) {
                createField(child, pendingDecorators)?.let {
                    frontend.scopeManager.addDeclaration(it)
                    record.addDeclaration(it)
                }
                pendingDecorators = null
                index++
                continue
            }

            val bodyNode = resolveMethodBodyNode(nextChild)
            if (isArkUiMethodSignature(child) && bodyNode != null) {
                createMethod(record, child, bodyNode, pendingDecorators)?.let {
                    frontend.scopeManager.addDeclaration(it)
                    record.addDeclaration(it)
                }
                pendingDecorators = null
                index += 2
                continue
            }

            pendingDecorators = null
            index++
        }

        frontend.scopeManager.leaveScope(record)

        return translationUnit
    }

    private fun isDecoratorCarrier(node: TypeScriptNode): Boolean {
        return node.type == "MissingDeclaration" &&
            node.children?.any { it.type == "Decorator" } == true
    }

    private fun hasDecorator(node: TypeScriptNode, name: String): Boolean {
        return node.children
            ?.filter { it.type == "Decorator" }
            ?.any { frontend.getIdentifierName(it) == name } == true
    }

    private fun isArkUiField(node: TypeScriptNode): Boolean {
        return node.type == "LabeledStatement" &&
            typedNameRegex.matches(frontend.codeOf(node) ?: "")
    }

    private fun isArkUiCallbackField(node: TypeScriptNode, valueNode: TypeScriptNode?): Boolean {
        return node.type == "LabeledStatement" &&
            typedNameRegex.matches(frontend.codeOf(node) ?: "") &&
            valueNode?.type == "ExpressionStatement" &&
            valueNode.firstChild("ArrowFunction") != null
    }

    private fun createField(node: TypeScriptNode, decorators: TypeScriptNode?): Field? {
        val match = typedNameRegex.find(frontend.codeOf(node) ?: "") ?: return null
        val name = match.groupValues[1]
        val type = typeFromText(match.groupValues[2].trim())

        val field = frontend.newField(name, type, emptySet<String>(), null, false, rawNode = node)
        decorators?.let { frontend.processAnnotations(field, it) }

        return field
    }

    private fun createCallbackMethod(
        record: Record,
        fieldNode: TypeScriptNode,
        valueNode: TypeScriptNode,
        decorators: TypeScriptNode?,
    ): Method? {
        val match = typedNameRegex.find(frontend.codeOf(fieldNode) ?: return null) ?: return null
        val name = match.groupValues[1]
        val arrowFunction = valueNode.firstChild("ArrowFunction") ?: return null
        val bodyNode = resolveMethodBodyNode(valueNode) ?: return null

        val method = frontend.newMethod(name, false, record, rawNode = valueNode)

        frontend.scopeManager.enterScope(method)

        arrowFunction.children
            ?.filter { it.type == "Parameter" }
            ?.forEach {
                val param = frontend.declarationHandler.handle(it) as? Parameter ?: return@forEach
                frontend.scopeManager.addDeclaration(param)
                method.parameters += param
            }

        method.body = frontend.statementHandler.handle(bodyNode)

        frontend.scopeManager.leaveScope(method)

        decorators?.let { frontend.processAnnotations(method, it) }

        return method
    }

    private fun isArkUiMethodSignature(node: TypeScriptNode): Boolean {
        if (node.type != "ExpressionStatement") {
            return false
        }

        val callExpr = node.firstChild("CallExpression") ?: return false
        val children = callExpr.children ?: return false

        return children.firstOrNull()?.type == "Identifier"
    }

    private fun resolveMethodBodyNode(node: TypeScriptNode?): TypeScriptNode? {
        if (node == null) {
            return null
        }

        if (node.type == "Block") {
            return node
        }

        node.firstChild("ArrowFunction")?.firstChild("Block")?.let {
            return it
        }

        if (
            node.type == "ExpressionStatement" &&
                frontend.codeOf(node)?.trim()?.startsWith("void {") == true
        ) {
            return synthesizeBlock(node)
        }

        return null
    }

    private fun synthesizeBlock(node: TypeScriptNode): TypeScriptNode? {
        val statements = mutableListOf<TypeScriptNode>()
        collectSyntheticStatements(node, node, statements)
        if (statements.isEmpty()) {
            return null
        }

        return TypeScriptNode("Block", statements, node.location, frontend.codeOf(node))
    }

    private fun collectSyntheticStatements(
        root: TypeScriptNode,
        node: TypeScriptNode,
        out: MutableList<TypeScriptNode>,
    ) {
        if (node !== root) {
            when (node.type) {
                "ExpressionStatement",
                "IfStatement",
                "ReturnStatement",
                "VariableStatement",
                "FirstStatement" -> {
                    out += node
                    return
                }
                "CallExpression" -> {
                    out +=
                        TypeScriptNode(
                            "ExpressionStatement",
                            listOf(node),
                            node.location,
                            frontend.codeOf(node),
                        )
                    return
                }
            }
        }

        node.children?.forEach { child -> collectSyntheticStatements(root, child, out) }
    }

    private fun createMethod(
        record: Record,
        signatureNode: TypeScriptNode,
        bodyNode: TypeScriptNode,
        decorators: TypeScriptNode?,
    ): Method? {
        val callExpr = signatureNode.firstChild("CallExpression") ?: return null
        val signatureChildren = callExpr.children ?: return null
        val name =
            frontend.codeOf(signatureChildren.firstOrNull() ?: return null)?.trim() ?: return null

        val method = frontend.newMethod(name, false, record, rawNode = signatureNode)

        frontend.scopeManager.enterScope(method)

        parseParameters(signatureChildren).forEach {
            frontend.scopeManager.addDeclaration(it)
            method.parameters += it
        }

        method.body = frontend.statementHandler.handle(bodyNode)

        frontend.scopeManager.leaveScope(method)

        decorators?.let { frontend.processAnnotations(method, it) }

        return method
    }

    private fun parseParameters(signatureChildren: List<TypeScriptNode>): List<Parameter> {
        val parameters = mutableListOf<Parameter>()
        var index = 1

        while (index < signatureChildren.size) {
            val nameNode = signatureChildren[index]
            if (nameNode.type != "Identifier") {
                index++
                continue
            }

            val typeNode = signatureChildren.getOrNull(index + 1)
            val name = frontend.codeOf(nameNode)?.trim().orEmpty()
            val type = typeNode?.let { typeFromNode(it) } ?: frontend.unknownType()
            parameters += frontend.newParameter(name, type, false, rawNode = nameNode)

            index += 2
        }

        return parameters
    }

    private fun typeFromNode(node: TypeScriptNode): Type {
        return when (node.type) {
            "StringKeyword" -> frontend.primitiveType("string")
            "NumberKeyword" -> frontend.primitiveType("number")
            "BooleanKeyword" -> frontend.primitiveType("boolean")
            "Identifier" -> typeFromText(frontend.codeOf(node)?.trim().orEmpty())
            else -> frontend.unknownType()
        }
    }

    private fun typeFromText(typeText: String): Type {
        return when (typeText) {
            "string" -> frontend.primitiveType("string")
            "number" -> frontend.primitiveType("number")
            "boolean" -> frontend.primitiveType("boolean")
            else -> frontend.unknownType()
        }
    }
}
