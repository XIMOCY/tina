import base64
import os


def normalize_path(path):
    if not path:
        return path
    return os.path.normpath(os.path.abspath(path))  # 建议增加 abspath 获取绝对路径


def build_multimodal_message(
    input_text: str = None,
    input_image: str | list[str] = None,
    input_audio: str | list[str] = None,
    input_url: str | list[str] = None,
    image_detail: str = "auto",
    role: str = "user",
):
    user_message = []

    # 1. 文本处理
    if input_text:
        user_message.append({"type": "text", "text": input_text})

    # 2. 本地图片列表处理
    if input_image:
        images = [input_image] if isinstance(input_image, str) else input_image
        # 定义支持的格式映射 (后缀: MIME类型)
        img_formats = {
            "png": "png",
            "jpg": "jpeg",
            "jpeg": "jpeg",
            "gif": "gif",
            "webp": "webp",
        }
        for img_path in images:
            img_path = normalize_path(img_path)
            if not os.path.exists(img_path):
                continue  # 跳过不存在的文件

            ext = img_path.split(".")[-1].lower()
            if ext in img_formats:
                mime_type = img_formats[ext]
                user_message.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/{mime_type};base64,{_encode_file(img_path)}",
                            "detail": image_detail,
                        },
                    }
                )

    if input_url:
        urls = [input_url] if isinstance(input_url, str) else input_url
        for url in urls:
            user_message.append({"type": "image_url", "image_url": {"url": url}})

    # 4. 本地音频列表处理
    if input_audio:
        audios = [input_audio] if isinstance(input_audio, str) else input_audio

        allowed_audios = {"wav", "mp3", "ogg", "m4a", "aac"}
        for aud_path in audios:
            aud_path = normalize_path(aud_path)
            if not os.path.exists(aud_path):
                continue

            audio_ext = aud_path.split(".")[-1].lower()
            if audio_ext in allowed_audios:
                user_message.append(
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": _encode_file(aud_path),
                            "format": audio_ext,
                        },
                    }
                )

    return {"role": role, "content": user_message} if user_message else None


def _encode_file(file_path: str) -> str:
    try:
        # 这里可以增加一个 os.path.getsize(file_path) 校验，例如超过 20MB 抛出警告
        with open(file_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        # 实际生产中建议用 logging，避免直接 print
        raise Exception(f"文件读取/编码失败: {file_path}, Error: {str(e)}")
