"""
Standalone parse_file implementation with no MatMaster dependencies.
Ready to be migrated to document parser MCP server.
"""
import asyncio
import base64
import mimetypes
import os
from typing import Optional, TypedDict
from urllib.parse import urlparse

import aiohttp
from litellm import acompletion

from .prompt import ParseFileInstruction


class ParseFileResponse(TypedDict):
    msg: str


# Configuration Constants
TEXT_FILE_MAX_SIZE = 1 * 1024 * 1024  # 1MB for text files
IMAGE_FILE_MAX_SIZE = 20 * 1024 * 1024  # 20MB for images

# Model for image parsing: from env or default (no MatMaster dependency)
DEFAULT_IMAGE_MODEL = 'gemini-2.0-flash'


def _filename_from_url(url: str) -> str:
    """Get filename from URL path for mimetype guessing. No HTTP request."""
    path = urlparse(url).path
    return path.rsplit('/', 1)[-1] if path else 'unknown'


async def _parse_image_content(
    content: bytes,
    mime_type: str,
    model_name: Optional[str] = None,
) -> str:
    """Handles visual parsing using the configured model."""
    b64_data = base64.b64encode(content).decode('utf-8')
    data_uri = f"data:{mime_type};base64,{b64_data}"

    name = model_name or os.environ.get('PARSE_FILE_IMAGE_MODEL', DEFAULT_IMAGE_MODEL)

    response = await acompletion(
        model=name,
        messages=[
            {
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': ParseFileInstruction},
                    {'type': 'image_url', 'image_url': {'url': data_uri}},
                ],
            }
        ],
        temperature=0.0,
    )
    return response.choices[0].message.content


async def _parse_text_content(content: bytes) -> str:
    """Handles text parsing by decoding the bytes content."""
    try:
        text_content = content.decode('utf-8')
        return text_content
    except UnicodeDecodeError:
        try:
            text_content = content.decode('gbk')
            return text_content
        except UnicodeDecodeError:
            return '无法解码文件内容：不支持的文本编码格式'


async def parse_file(
    file_url: str,
    model_name: Optional[str] = None,
) -> ParseFileResponse:
    """
    Download file from URL and parse as text or image.
    MCP tool name: parse_file. No MatMaster dependencies.
    """
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                file_url, timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                filename = _filename_from_url(file_url)
                mime_type, _ = mimetypes.guess_type(filename)

                max_size = (
                    IMAGE_FILE_MAX_SIZE
                    if mime_type and mime_type.startswith('image/')
                    else TEXT_FILE_MAX_SIZE
                )

                if resp.content_length and resp.content_length > max_size:
                    return ParseFileResponse(
                        msg=f'文件超出大小限制（>{max_size} 字节）'
                    )

                content = await resp.read()
                if len(content) > max_size:
                    return ParseFileResponse(
                        msg=f'文件超出大小限制（>{max_size} 字节）'
                    )

                if mime_type and mime_type.startswith('image/'):
                    result = await _parse_image_content(
                        content, mime_type, model_name=model_name
                    )
                else:
                    result = await _parse_text_content(content)

                return ParseFileResponse(msg=str(result))

        except asyncio.TimeoutError:
            return ParseFileResponse(msg='请求超时，请检查网络或文件地址')
        except Exception as e:
            return ParseFileResponse(msg=f'解析错误: {str(e)}')


if __name__ == '__main__':
    asyncio.run(
        parse_file(
            'https://dp-storage-test2.oss-cn-zhangjiakou.aliyuncs.com/bohrium-test/bohrium/feedback/attachment/01KBM1X4KGDHTE2ZR44G7EHC0Z/dsc-example.txt'
        )
    )
    asyncio.run(
        parse_file(
            'https://bohrium.oss-cn-zhangjiakou.aliyuncs.com/bohrium/feedback/attachment/01KF8EZX821J2MVRGPZ9PG4JY8/screenshot-20260118-194811.png'
        )
    )
