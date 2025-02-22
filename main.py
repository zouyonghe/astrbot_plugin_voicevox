import re
import tempfile
import aiohttp
import os

from astrbot.api.all import *


@register("VoicevoxTTS", "Text-to-Speech", "基于VOICEVOX Engine的文本转语音插件", "1.0.0")
class VoicevoxTTSGenerator(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.session = None
        self._validate_config()

    def _validate_config(self):
        """配置验证"""
        if not self.config.get("voicevox_url"):
            raise ValueError("请提供VOICEVOX Engine的API地址")
        self.config["voicevox_url"] = self.config["voicevox_url"].strip()
        if self.config["voicevox_url"].endswith("/"):
            self.config["voicevox_url"] = self.config["voicevox_url"].rstrip("/")

    async def ensure_session(self):
        """确保会话连接"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(self.config.get("session_timeout_time", 120))
            )

    async def _call_voicevox_api(self, text: str, speaker: int) -> bytes:
        """调用VOICEVOX Engine API"""
        payload = {"text": text, "speaker": speaker}
        await self.ensure_session()
        try:
            async with self.session.post(f"{self.config['voicevox_url']}/audio_query", json=payload) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    raise ConnectionError(f"API错误 ({resp.status}): {error}")
                audio_query = await resp.json()

            async with self.session.post(f"{self.config['voicevox_url']}/synthesis", json=audio_query) as audio_resp:
                if audio_resp.status != 200:
                    error = await audio_resp.text()
                    raise ConnectionError(f"音频合成错误 ({audio_resp.status}): {error}")
                return await audio_resp.read()
        except aiohttp.ClientError as e:
            raise ConnectionError(f"连接失败: {str(e)}")

    async def _list_speakers(self):
        """列出可用的讲话者"""
        await self.ensure_session()
        try:
            async with self.session.get(f"{self.config['voicevox_url']}/speakers") as resp:
                if resp.status != 200:
                    raise ConnectionError(f"无法获取讲话者列表 (状态码: {resp.status})")
                return await resp.json()
        except aiohttp.ClientError as e:
            raise ConnectionError(f"连接失败: {str(e)}")

    @command_group("voicevox")
    def voicevox(self):
        pass

    @voicevox.command("gen")
    async def generate_speech(self, event: AstrMessageEvent, text: str):
        """生成语音
        Args:
            text: 要生成的语音内容
        """
        try:
            speaker = self.config.get("default_speaker", 1)
            audio_data = await self._call_voicevox_api(text, speaker)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
                temp_audio.write(audio_data)
                temp_audio_path = temp_audio.name

            chain = [
                Record(file=temp_audio_path),
            ]
            yield event.chain_result(chain)
            os.remove(temp_audio_path)
        except Exception as e:
            logger.error(f"生成语音失败: {e}")
            yield event.plain_result("❌ 语音生成失败，请检查日志")

    @voicevox.command("speakers")
    async def list_speakers(self, event: AstrMessageEvent):
        """列出可用音声"""
        try:
            speakers = await self._list_speakers()
            speakers_list = "\n".join(f"{i + 1}. {speaker['name']}" for i, speaker in enumerate(speakers))
            yield event.plain_result(f"可用音声列表:\n{speakers_list}")
        except Exception as e:
            logger.error(f"获取音声列表失败: {e}")
            yield event.plain_result("❌ 获取音声列表失败，请检查日志")

    @voicevox.command("set_speaker")
    async def set_speaker(self, event: AstrMessageEvent, speaker_index: int):
        """设置默认音声"""
        try:
            speakers = await self._list_speakers()
            index = int(speaker_index) - 1
            if index < 0 or index >= len(speakers):
                yield event.plain_result("❌ 无效的音声索引，请先使用 /voicevox speakers 查看音声列表")
                return

            selected_speaker = speakers[index]["id"]
            self.config["default_speaker"] = selected_speaker
            yield event.plain_result(f"✅ 音声已设置为: {speakers[index]['name']}")
        except Exception as e:
            logger.error(f"设置音声失败: {e}")
            yield event.plain_result("❌ 设置音声失败，请检查日志")

    # @filter.on_decorating_result()
    # async def on_decorating_result(self, event: AstrMessageEvent):
    #     # 插件是否启用
    #     if not self.enabled:
    #         return
    #
    #     # 获取事件结果
    #     result = event.get_result()
    #     # 初始化plain_text变量
    #     plain_text = ""
    #     chain = result.chain
    #
    #     #遍历组件
    #     for comp in result.chain:
    #         if isinstance(comp, Image):  # 检测是否有Image组件
    #             chain.append(Plain("检测到图片冲突，终止语音转换"))
    #             return
    #         if isinstance(comp, Plain):
    #             cleaned_text = re.sub(r'[()《》#%^&*+-_{}]', '', comp.text)
    #             plain_text += cleaned_text
    #
    #             result.chain = [Record(file=str(output_audio_path))]
    #     except Exception as e:
    #         logger.error(f"语音转换失败: {e}")
    #         chain.append(Plain("语音转换失败，请稍后再试"))