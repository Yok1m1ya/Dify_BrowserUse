import asyncio
import os
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from browser_use import Agent, BrowserSession
from langchain_openai import ChatOpenAI

class DifyBrowseruseTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            # 获取用户输入的查询指令
            query = tool_parameters.get('query', '').strip()
            if not query:
                yield self.create_text_message('❌ 请提供有效的查询指令')
                return
            # 发送开始执行的消息
            yield self.create_text_message(f'🚀 开始执行浏览器自动化任务: {query}')
            # 调用Browser-Use执行操作
            result = asyncio.run(self._execute_browser_use(query))
            # 发送执行结果
            yield self.create_json_message({
                "task": query,
                "result": result,
                "status": "completed"
            })
        except Exception as e:
            yield self.create_text_message(f'❌ 执行失败: {str(e)}')

    async def _execute_browser_use(self, query: str) -> str:
        try:
            # 设置扩展系统提示
            extend_planner_system_message = """
            以下为重要的规则:
            1.最后的输出结果,使用中文回答用户。
            2.如果遇见付费墙,验证码验证或登录限制时直接跳过并说明情况。
            """
            # 绕过browser-use的OpenAI API key检查
            os.environ["OPENAI_API_KEY"] = "fake_key"
            # 初始化LLM - 使用公司内部模型
            llm = self._initialize_llm()
            browser = BrowserSession()
            if not llm:
                return "❌ LLM配置失败,请检查内部模型服务"
            # 创建Browser-Use Agent - 让Agent自己管理浏览器
            agent = Agent(
                task=query,
                llm=llm,
                use_vision=False,
                browser_session=browser,
                extend_planner_system_message=extend_planner_system_message,
            )
            # 执行任务
            history = await agent.run()
            # 处理返回结果
            if hasattr(history.final_result(), 'message'):
                return history.final_result.message
            elif isinstance(history.final_result, str):
                return history.final_result
            else:
                return f"✅ 任务执行完成: {query}"
        except Exception as inner_e:
            return f"❌ 浏览器操作执行失败: {str(inner_e)}"
        except Exception as e:
            return f"❌ Browser-Use执行出错: {str(e)}"


    def _initialize_llm(self):
        try:
            # 使用公司内部的DeepSeek模型
            llm = ChatOpenAI(
                model="DeepSeek",
                openai_api_base="http://10.4.35.35:31111/v1",
            )
            return llm
        except Exception as e:
            print(f"LLM初始化失败: {str(e)}")
            return None

    def _initialize_browser(self):
        try:
            browser_session = BrowserSession(
                headless=True,
                viewport={'width': 964, 'height': 647},
            )
            return browser_session
        except Exception as e:
            print(f"Browser初始化失败：: {str(e)}")
            return None