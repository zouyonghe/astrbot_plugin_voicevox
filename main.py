import re
import tempfile

import aiohttp

from astrbot.api.all import *
from astrbot.api.event.filter import *

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

    def _is_japanese(self, text):
        japanese_pattern = re.compile(r'[\u3040-\u309F\u30A0-\u30FF]')  # 假名范围
        japanese_kanji_pattern = re.compile(r'[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]')  # 日语汉字范围（含扩展A+B+C等）
        chinese_pattern = re.compile(r'^[\u4E00-\u9FFF，。！？、；：]*$')  # 纯中文（允许全角标点）
        # 是否包含假名
        contains_kana = japanese_pattern.search(text)
        # 是否包含日语汉字
        contains_japanese_kanji = japanese_kanji_pattern.search(text)
        # 是否为纯中文
        is_pure_chinese = chinese_pattern.fullmatch(text)

        # 条件：包含假名，或包含日语汉字但文本不只是纯中文
        if contains_kana or (contains_japanese_kanji and not is_pure_chinese):
            return True

        return False

    async def _call_voicevox_api(self, text: str, speaker: int) -> bytes:
        """调用 VOICEVOX Engine API，生成语音"""
        await self.ensure_session()
        voicevox_url = self.config["voicevox_url"]
        try:
            # 第一步：调用 audio_query 接口，获取查询参数
            url_query = f"{voicevox_url}/audio_query"
            params = {
                "text": text,  # 提供文本
                "speaker": speaker  # 提供风格ID
            }
            async with self.session.post(url_query, params=params) as resp_query:
                if resp_query.status != 200:
                    error = await resp_query.text()
                    raise ConnectionError(f"audio_query 请求失败: ({resp_query.status}) {error}")
                audio_query = await resp_query.json()  # 获取 audio_query 接口的返回值

            # 第二步：调用 synthesis 接口，生成音频
            url_synthesis = f"{voicevox_url}/synthesis"
            params = {
                "speaker": speaker  # 提供风格ID
            }
            async with self.session.post(url_synthesis, json=audio_query, params=params) as resp_synthesis:
                if resp_synthesis.status != 200:
                    error = await resp_synthesis.text()
                    raise ConnectionError(f"synthesis 请求失败: ({resp_synthesis.status}) {error}")
                return await resp_synthesis.read()  # 返回生成的音频数据（二进制）

        except aiohttp.ClientError as e:
            raise ConnectionError(f"与 VOICEVOX API 通信失败: {str(e)}")

    async def _list_speakers(self):
        """列出可用的音声"""
        await self.ensure_session()
        try:
            async with self.session.get(f"{self.config['voicevox_url']}/speakers") as resp:
                if resp.status != 200:
                    raise ConnectionError(f"无法获取音声风格信息 (状态码: {resp.status})")
                return await resp.json()
        except aiohttp.ClientError as e:
            raise ConnectionError(f"连接失败: {str(e)}")

    async def _get_speaker_id(self):
        """获取对应的 speaker_id"""
        # 检查是否已设置默认音声和样式
        voice = self.config.get("default_voice")  # 配置中保存的音声名称
        style = self.config.get("default_style")  # 配置中保存的样式名称
        if not voice or not style:
            raise ValueError(f"未设置音声或风格")

        speakers = await self._list_speakers()

        # Find speaker by voice name
        speaker = next((s for s in speakers if s["name"] == voice), None)
        if not speaker:
            raise ValueError(f"找不到音声 {voice}")

        # Find style by style name
        style_obj = next((s for s in speaker["styles"] if s["name"] == style), None)
        if not style_obj:
            raise ValueError(f"音声 {voice} 下找不到风格 {style}")

        return style_obj["id"]

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

            # 验证是否为日语文本
            if not self._is_japanese(text):
                yield event.plain_result("⚠️ VOICEVOX 只支持日语文本转语音，请提供日语文本。")
                return

            # 获取 speaker ID
            speaker_id = await self._get_speaker_id()

            # 调用 API 生成语音
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
            styles_list = "\n".join([f"{i + 1}. {style['name']} (风格ID: {style['id']})"
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

    @on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent):
        # 获取事件结果
        plain_text = ""

        # 遍历组件
        for comp in event.get_result().chain:
            if not isinstance(comp, Plain):  # 检测是否包含文字外其他内容
                return
            else:
                plain_text += comp.toString()
                logger.error(f"plain_text: {plain_text}")

        # 验证是否为日语文本
        if not self._is_japanese(plain_text):
            return

        try:
            # 获取默认的 speaker_id
            speaker_id = await self._get_speaker_id()

            # 调用 API 生成语音
            audio_data = await self._call_voicevox_api(text=plain_text, speaker=speaker_id)

            # 使用临时文件存储音频
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
                temp_audio.write(audio_data)
                temp_audio_path = temp_audio.name

            # 将生成的音频文件添加到事件链
            event.get_result().chain = [Record(file=temp_audio_path)]
            os.remove(temp_audio_path)  # 清理临时文件
        except Exception as e:
            logger.error(f"转换失败，输入文本: {plain_text}, 错误信息: {e}")
