#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
browser_worker_file.py - 基于文件通信的Browser-Use执行脚本
通过文件进行输入输出，完全避免stdout/stderr的编码问题
简化版 - 去除浏览器验证和安装部分
"""

import asyncio
import sys
import json
import os
import traceback
from pathlib import Path

# 设置UTF-8编码
os.environ["PYTHONIOENCODING"] = "utf-8"

# 添加当前目录到Python路径
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# 禁用遥测
os.environ["ANONYMIZED_TELEMETRY"] = "false"

try:
    from browser_use import Agent, BrowserSession
    from langchain_openai import ChatOpenAI

    print("✅ 成功导入browser_use和langchain_openai")
except ImportError as e:
    # 如果导入失败，写入错误到输出文件
    print(f"❌ 导入模块失败: {str(e)}")
    if len(sys.argv) >= 3:
        output_file = Path(sys.argv[2])
        error_result = {
            "success": False,
            "task": "",
            "result": "",
            "error": f"导入模块失败: {str(e)}"
        }
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(error_result, f, ensure_ascii=False, indent=2)
            print(f"✅ 错误信息已写入: {output_file}")
        except Exception as write_error:
            print(f"❌ 写入错误文件失败: {write_error}")
    sys.exit(1)


async def execute_browser_task(query: str, task_id: str) -> dict:
    """执行Browser-Use任务的异步方法"""
    browser_session = None
    agent = None

    try:
        print(f"🔧 Worker进程开始执行任务ID: {task_id}")
        print(f"📋 任务内容: {query}")

        # 初始化LLM
        try:
            llm = ChatOpenAI(
                model="DeepSeek",
                openai_api_base="http://10.4.35.64:31111/v1",
                timeout=30,
                max_retries=3,
            )
            print("✅ LLM初始化完成")
        except Exception as llm_error:
            print(f"❌ LLM初始化失败: {llm_error}")
            return {
                "success": False,
                "task": query,
                "result": "",
                "error": f"LLM初始化失败: {str(llm_error)}"
            }

        # Docker环境必需的浏览器启动参数
        browser_args = [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu',
            '--ignore-certificate-errors',
            '--ignore-ssl-errors',
            '--disable-web-security',
            '--allow-running-insecure-content',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding',
            '--disable-features=TranslateUI',
            '--disable-ipc-flooding-protection',
            '--disable-hang-monitor',
            '--disable-client-side-phishing-detection',
            '--disable-popup-blocking',
            '--disable-prompt-on-repost',
            '--disable-sync',
            '--disable-extensions',
            '--disable-plugins',
            '--disable-images',
            '--disable-javascript-harmony-shipping',
            '--disable-background-networking',
            '--disable-default-apps',
            '--disable-translate',
            '--disable-device-discovery-notifications',
            '--disable-software-rasterizer',
            '--disable-webgl',
            '--disable-threaded-animation',
            '--disable-threaded-scrolling',
            '--disable-in-process-stack-traces',
            '--disable-histogram-customizer',
            '--disable-gl-extensions',
            '--disable-composited-antialiasing',
            '--disable-canvas-aa',
            '--disable-3d-apis',
            '--disable-accelerated-2d-canvas',
            '--disable-accelerated-jpeg-decoding',
            '--disable-accelerated-mjpeg-decode',
            '--disable-app-list-dismiss-on-blur',
            '--disable-accelerated-video-decode',
            '--num-raster-threads=1',
            '--max_old_space_size=1024',
            '--single-process',
            '--no-zygote',
            '--memory-pressure-off'
        ]

        try:
            # 初始化浏览器会话
            print("🔧 开始初始化浏览器会话...")
            browser_session = BrowserSession(
                headless=True,
                viewport={'width': 1280, 'height': 720},
                context_options={
                    "ignoreHTTPSErrors": True,
                    "acceptDownloads": True,
                    "bypassCSP": True,
                },
                keep_alive=True,
                args=browser_args
            )
            print("✅ 浏览器会话配置完成")

            print("🚀 启动浏览器会话...")
            await browser_session.start()
            print("✅ 浏览器会话启动成功")

        except Exception as browser_start_error:
            error_msg = f"浏览器启动失败: {str(browser_start_error)}"
            print(f"❌ {error_msg}")
            print(f"📋 详细错误: {traceback.format_exc()}")
            return {
                "success": False,
                "task": query,
                "result": "",
                "error": error_msg
            }

        # 系统消息配置
        extend_system_message = """
        记住最重要的规则:
        1. 永远不要自动填入任何登录信息，除非用户提供了账户名及密码。
        2. 最后的输出结果,使用中文回答用户。
        3. 专注于快速获取页面的主要内容和信息。
        4. 避免执行不必要的复杂操作。
        """

        extend_planner_system_message = """
        以下为补充的重要规则:
        1. 如果遇见"你的连接不是专用连接"、"不安全"、"证书错误"等安全警告页面:
           - 立即寻找"高级"、"Advanced"、"详细信息"等按钮并点击
           - 然后寻找"继续访问"、"继续前往"、"Proceed to"等链接并点击
           - 这些操作是必须的，不要跳过
        2. 如果页面加载失败，请重试一次。
        3. 专注于获取页面的主要内容和信息。
        4. 尽量在5步以内完成任务。
        5. 如果页面加载缓慢，等待最多10秒后继续。
        """

        # 创建Browser-Use Agent
        try:
            print("🤖 创建Agent...")
            agent = Agent(
                task=query,
                llm=llm,
                use_vision=False,
                browser_session=browser_session,
                extend_system_message=extend_system_message,
                extend_planner_system_message=extend_planner_system_message
            )
            print("✅ Agent创建完成")
        except Exception as agent_error:
            print(f"❌ Agent创建失败: {agent_error}")
            return {
                "success": False,
                "task": query,
                "result": "",
                "error": f"Agent创建失败: {str(agent_error)}"
            }

        try:
            print("🎯 开始执行任务...")
            history = await agent.run()
            print("✅ 任务执行完成")
        except Exception as run_error:
            print(f"❌ 任务执行失败: {run_error}")
            return {
                "success": False,
                "task": query,
                "result": "",
                "error": f"任务执行失败: {str(run_error)}"
            }

        # 获取最终结果
        final_result = history.final_result()
        print(f"📋 获取到final_result: {bool(final_result)}")

        if final_result:
            return {
                "success": True,
                "task": query,
                "result": str(final_result),
                "error": ""
            }

        # 备用方案1：从extracted_content获取
        extracted_content = history.extracted_content()
        print(f"📋 获取到extracted_content: {len(extracted_content) if extracted_content else 0}条")

        if extracted_content:
            last_content = extracted_content[-1] if extracted_content else "未找到提取的内容"
            return {
                "success": True,
                "task": query,
                "result": str(last_content),
                "error": ""
            }

        # 备用方案2：检查完成状态
        is_done = history.is_done()
        print(f"📋 任务完成状态: {is_done}")

        if is_done:
            return {
                "success": True,
                "task": query,
                "result": "任务已完成，但未获取到具体结果内容",
                "error": ""
            }
        else:
            return {
                "success": False,
                "task": query,
                "result": "",
                "error": "任务未完成"
            }

    except Exception as e:
        error_msg = f"Agent执行错误: {str(e)}"
        print(f"❌ {error_msg}")
        print(f"📋 错误详情: {traceback.format_exc()}")
        return {
            "success": False,
            "task": query,
            "result": "",
            "error": error_msg
        }

    finally:
        # 确保浏览器会话被正确关闭
        print("🧹 开始清理资源...")
        try:
            if agent and hasattr(agent, 'browser_session') and agent.browser_session:
                await agent.browser_session.close()
                print("✅ Agent的浏览器会话已关闭")
            elif browser_session:
                await browser_session.close()
                print("✅ 浏览器会话已关闭")
        except Exception as cleanup_error:
            print(f"⚠️ 清理资源时出错: {str(cleanup_error)}")


def main():
    """主函数"""
    print("🚀 开始执行main函数...")

    if len(sys.argv) != 3:
        print("❌ 参数错误")
        print("使用方法: python browser_worker_file.py <input_file> <output_file>")
        sys.exit(1)

    input_file = Path(sys.argv[1])
    output_file = Path(sys.argv[2])

    print(f"📁 输入文件: {input_file}")
    print(f"📁 输出文件: {output_file}")

    try:
        # 读取任务文件
        if not input_file.exists():
            raise FileNotFoundError(f"输入文件不存在: {input_file}")

        print("📖 读取任务文件...")
        with open(input_file, 'r', encoding='utf-8') as f:
            task_data = json.load(f)

        query = task_data.get('query', '')
        task_id = task_data.get('task_id', 'unknown')

        print(f"📋 任务ID: {task_id}")
        print(f"📋 查询内容: {query}")

        if not query:
            raise ValueError("任务查询内容为空")

        # 执行任务
        print("🎯 开始执行异步任务...")
        result = asyncio.run(execute_browser_task(query, task_id))
        print(f"✅ 任务执行完成，结果: {result}")

        # 写入结果文件
        print(f"💾 写入结果到: {output_file}")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"✅ 任务完成，结果已写入: {output_file}")

    except KeyboardInterrupt:
        print("🛑 收到中断信号，正在退出...")
        error_result = {
            "success": False,
            "task": "",
            "result": "",
            "error": "任务被用户中断"
        }
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(error_result, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        sys.exit(1)

    except Exception as e:
        print(f"💥 主函数异常: {str(e)}")
        print(f"📋 异常详情: {traceback.format_exc()}")
        error_result = {
            "success": False,
            "task": "",
            "result": "",
            "error": f"执行异常: {str(e)}"
        }
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(error_result, f, ensure_ascii=False, indent=2)
            print(f"✅ 错误信息已写入: {output_file}")
        except Exception as write_error:
            print(f"❌ 写入错误文件失败: {write_error}")
        sys.exit(1)


if __name__ == "__main__":
    print("=" * 50)
    print("🎬 Browser Worker 启动")
    print("=" * 50)
    main()