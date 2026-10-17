package com.aliothmoon.maafw.project

import com.aliothmoon.maafw.domain.*
import com.aliothmoon.maafw.runner.RunPlanBuilder
import com.aliothmoon.maafw.runner.RunPlanResult
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.*
import org.junit.Test
import java.io.File

/** 使用真正的安卓 PI 解析器和执行计划编译器检查生成资源。 */
class MaaFgoCompatibilityTest {
    private fun definition(): ProjectDefinition {
        val root = File(requireNotNull(System.getenv("MAAFGO_COMPAT_ASSETS")))
        val loaded = ProjectLoader(DirectoryProjectSource(root)).load()
        assertTrue("项目加载失败: $loaded", loaded is ProjectLoadResult.Ready)
        val ready = loaded as ProjectLoadResult.Ready
        assertTrue("解析错误: ${ready.diagnostics}", ready.diagnostics.none { it.severity == DiagnosticSeverity.Error })
        return ready.definition
    }

    private fun compile(definition: ProjectDefinition, task: String, values: Map<String, OptionValue>): RunPlanResult.Success {
        val id = RunConfigurationId("compatibility")
        val config = UserConfiguration(
            initialized = true, activeResourceName = "日服", activeConfigurationId = id,
            configurations = listOf(RunConfiguration(id, "兼容检查", listOf(ConfiguredTask(task, enabled = true, optionValues = values)))),
        )
        val result = RunPlanBuilder.build(definition, config)
        assertTrue("任务编译失败: $result", result is RunPlanResult.Success)
        return result as RunPlanResult.Success
    }

    @Test fun sixFileListsKeepIconsDefaultsAndAgentFilenames() {
        val definition = definition()
        for (prefix in listOf("普通助战-礼装", "冠位助战-1号礼装", "冠位助战-2号礼装")) {
            for (status in listOf("满破", "非满破")) {
                val name = "$prefix-$status"
                val option = definition.options[name] as OptionDefinition.Select
                assertEquals("0_空.png", option.defaultCase)
                assertEquals(47, option.cases.size)
                assertNotNull(option.cases.first().icon)
                val filename = option.cases.first { it.name != "0_空.png" }.name
                val values = mapOf(
                    "battle_mode" to OptionValue.SingleCase("native"),
                    "原生自动战斗助战方式" to OptionValue.SingleCase("自定义助战"),
                    "助战类型" to OptionValue.SingleCase(if (prefix.startsWith("普通")) "normal" else "grand"),
                    "普通助战-礼装" to OptionValue.SingleCase(status),
                    "冠位助战-1号礼装" to OptionValue.SingleCase(status),
                    "冠位助战-2号礼装" to OptionValue.SingleCase(status),
                    name to OptionValue.SingleCase(filename),
                )
                val plan = compile(definition, "直接bbc战斗", values).plan
                val attached = plan.tasks.single().pipelineOverrides.mapNotNull { patch ->
                    patch["助战action"]?.jsonObject?.get("attach")?.jsonObject?.get(name)
                }
                assertEquals("$name 未传给 Agent", filename, attached.last().jsonPrimitive.content)
            }
        }
    }

    @Test fun chaldeaTextInputIsSubstitutedAndGuideIsVisible() {
        val definition = definition()
        val source = "/sdcard/Download/队伍\"测试.json"
        val values = mapOf("Chaldea导入手动输入" to OptionValue.Inputs(mapOf("chaldea_import_source" to source)))
        val plan = compile(definition, "Chaldea 自动编队", values).plan
        val attached = plan.tasks.single().pipelineOverrides.mapNotNull { patch ->
            patch["执行自动编队"]?.jsonObject?.get("attach")?.jsonObject?.get("chaldea_import_source")
        }
        assertEquals(source, attached.last().jsonPrimitive.content)
        assertTrue(definition.task("Chaldea 自动编队")!!.description!!.contains("## 适用入口"))
    }
}
