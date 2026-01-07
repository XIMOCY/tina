import base64


def build_multimodal_message(input_text:str, 
                              input_image:str | list[str], 
                              input_audio:str | list[str], 
                              input_url:str | list[str], 
                              role:str):
        """
        快速生成多模态消息格式，可以直接append到messages中
        Args:
            input_text (str): 文本输入
            input_image (str | list[str]): 本地图片路径列表
            input_audio (str | list[str]): 本地音频路径列表
            input_url (str | list[str]): URL列表
            role (str): 角色
        return: list[dict]
        """
        user_message = []
        # 1. 文本
        if input_text:
            user_message.append({"type": "text", "text": input_text})

        # 2. 本地图片列表处理
        if input_image:
            images = [input_image] if isinstance(input_image, str) else input_image
            for img_path in images:
                ext = img_path.split('.')[-1].lower()
                if ext == 'jpg': ext = 'jpeg'
                user_message.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/{ext};base64,{_encode_file(img_path)}"}
                })

        # 3. 网络 URL 列表处理
        if input_url:
            urls = [input_url] if isinstance(input_url, str) else input_url
            for url in urls:
                user_message.append({"type": "image_url", "image_url": {"url": url}})

        # 4. 本地音频列表处理
        if input_audio:
            audios = [input_audio] if isinstance(input_audio, str) else input_audio
            for aud_path in audios:
                audio_ext = aud_path.split('.')[-1].lower()
                if audio_ext not in ['wav', 'mp3']: audio_ext = 'wav'
                user_message.append({
                    "type": "input_audio",
                    "input_audio": {"data": _encode_file(aud_path), "format": audio_ext}
                })

        return {"role": role, "content": user_message}
def _encode_file(file_path: str) -> str:
    """统一的 Base64 编码方法"""
    try:
        with open(file_path, "rb") as f:
            return base64.b64encode(f.read()).decode('utf-8')
    except Exception as e:
        raise Exception(f"文件编码失败: {str(e)}")