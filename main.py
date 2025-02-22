import tempfile

import aiohttp

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
        """列出可用的音声"""
        await self.ensure_session()
        try:
            async with self.session.get(f"{self.config['voicevox_url']}/speakers") as resp:
                if resp.status != 200:
                    raise ConnectionError(f"无法获取音声列表 (状态码: {resp.status})")
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
            # 验证输入文本是否为空
            if not text.strip():
                yield event.plain_result("❌ 生成语音失败：文本内容不能为空！")
                return

            # 检查是否已设置默认音声和样式
            voice_name = self.config.get("default_voice")  # 配置中保存的音声名称
            style_name = self.config.get("default_style")  # 配置中保存的样式名称
            if voice_name is None or style_name is None:
                yield event.plain_result("❌ 生成语音失败：请先设置音声和样式！")
                return

            # 获取音声和样式的 ID
            speakers = await self._list_speakers()
            speaker = next((s for s in speakers if s["name"] == voice_name), None)
            if not speaker:
                yield event.plain_result(f"❌ 找不到音声 {voice_name}，请检查设置！")
                return

            style = next((s for s in speaker["styles"] if s["name"] == style_name), None)
            if not style:
                yield event.plain_result(f"❌ 音声 {voice_name} 下找不到样式 {style_name}，请检查设置！")
                return

            # 调用 API 生成语音
            speaker_id = style["id"]
            audio_data = await self._call_voicevox_api(text, speaker_id)

            # 保存生成的音频
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
                temp_audio.write(audio_data)
                temp_audio_path = temp_audio.name

            # 返回生成的音频
            chain = [Record(file=temp_audio_path)]
            yield event.chain_result(chain)
            os.remove(temp_audio_path)
        except Exception as e:
            logger.error(f"生成语音失败: {e}")
            yield event.plain_result("❌ 语音生成失败，请检查日志")

    @voicevox.group("voice")
    def voice(self):
        pass

    @voice.command("list")
    async def list_voices(self, event: AstrMessageEvent):
        """列出所有可用的音声"""
        try:
            speakers = await self._list_speakers()
            speakers_list = "\n".join([f"{i + 1}. {speaker['name']}" for i, speaker in enumerate(speakers)])
            yield event.plain_result(f"可用音声列表:\n{speakers_list}")
        except Exception as e:
            logger.error(f"获取音声列表失败: {e}")
            yield event.plain_result("❌ 获取音声列表失败，请检查日志")

    @voice.command("set")
    async def set_voice(self, event: AstrMessageEvent, voice_index: int):
        """设置默认音声"""
        try:
            speakers = await self._list_speakers()
            index = int(voice_index) - 1

            if index < 0 or index >= len(speakers):
                yield event.plain_result("❌ 无效的音声索引，请先使用 /speakers voice list 查看音声列表")
                return

            selected_voice = speakers[index]["name"]
            self.config["default_voice"] = selected_voice  # 保存音声名称
            yield event.plain_result(f"✅ 默认音声已设置为: {selected_voice}")
        except Exception as e:
            logger.error(f"设置音声失败: {e}")
            yield event.plain_result("❌ 设置音声失败，请检查日志")

    @voicevox.group("style")
    def style(self):
        pass

    @style.command("list")
    async def list_styles(self, event: AstrMessageEvent):
        """列出当前默认音声的所有风格"""
        try:
            # 检查是否设置了默认音声
            voice_name = self.config.get("default_voice")  # 从配置获取默认音声名称
            if voice_name is None:
                yield event.plain_result("❌ 请先设置默认音声！使用 /voicevox set_voice <音声索引>")
                return

            # 获取音声列表并找到默认音声
            speakers = await self._list_speakers()
            speaker = next((s for s in speakers if s["name"] == voice_name), None)
            if not speaker:
                yield event.plain_result(f"❌ 找不到音声 {voice_name}，请重新设置！")
                return

            # 列出风格
            styles_list = "\n".join([f"{i + 1}. 风格名称: {style['name']} (风格ID: {style['id']})"
                                     for i, style in enumerate(speaker["styles"])])
            yield event.plain_result(f"音声 {voice_name} 的可用风格:\n{styles_list}")
        except Exception as e:
            logger.error(f"获取风格列表失败: {e}")
            yield event.plain_result("❌ 获取风格列表失败，请检查日志")

    @style.command("set")
    async def set_style(self, event: AstrMessageEvent, style_index: int):
        """设置当前音声的默认风格"""
        try:
            # 检查是否设置了默认音声
            voice_name = self.config.get("default_voice")  # 从配置获取默认音声名称
            if voice_name is None:
                yield event.plain_result("❌ 请先设置音声！使用 /voicevox set_voice <音声索引>")
                return

            # 获取音声及其样式列表
            speakers = await self._list_speakers()
            speaker = next((s for s in speakers if s["name"] == voice_name), None)
            if not speaker:
                yield event.plain_result(f"❌ 找不到音声 {voice_name}，请重新设置！")
                return

            # 检查索引并获取对应风格
            styles = speaker["styles"]
            index = int(style_index) - 1  # 用户输入的索引从 1 开始，调整为从 0 开始
            if index < 0 or index >= len(styles):
                yield event.plain_result("❌ 无效的风格索引，请使用 /voicevox list_styles 查看当前音声的风格")
                return

            # 设置默认风格
            selected_style = styles[index]["name"]
            self.config["default_style"] = selected_style  # 保存风格名称
            yield event.plain_result(f"✅ 默认风格已设置为: {selected_style}")
        except Exception as e:
            logger.error(f"设置风格失败: {e}")
            yield event.plain_result("❌ 设置风格失败，请检查日志")

