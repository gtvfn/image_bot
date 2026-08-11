import asyncio
import logging
import os
import uuid

import replicate
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

# ==== SETTINGS ====
# Put your tokens here, or set them via environment variables
TELEGRAM_TOKEN = os.getenv(
    "TELEGRAM_TOKEN", "YOUR_TG_TOKEN"
)
REPLICATE_API_TOKEN = os.getenv(
    "REPLICATE_API_TOKEN", "YOUR_API_TOKEN"
)

os.environ["REPLICATE_API_TOKEN"] = REPLICATE_API_TOKEN

# Models on Replicate
# nightmareai/real-esrgan, flux-kontext-apps/text-removal, and black-forest-labs/flux-kontext-pro
# are officially deployed models, so they can be called with just "owner/name" (Replicate
# resolves the latest version automatically). 851-labs/background-remover and
# philz1337x/clarity-upscaler are regular community models without that shortcut, so their
# version MUST be specified via "owner/name:version", otherwise Replicate returns 404. The
# current version can be found on the model's page on replicate.com under "API".
UPSCALE_MODEL = "nightmareai/real-esrgan"  # regular upscale (2x / 4x)
ARTISTIC_UPSCALE_MODEL = "philz1337x/clarity-upscaler:dfad41707589d68ecdccd1dfa600d55a208f9310748e44bfe35b4a6291453d5e"  # artistic upscale
BG_REMOVE_MODEL = "851-labs/background-remover:a029dff38972b5fda4ec5d75d7d1cd25aeff621d2cf4946a41055d7db66b80bc"  # background removal
TEXT_REMOVE_MODEL = "flux-kontext-apps/text-removal"  # text removal
EDIT_MODEL = "black-forest-labs/flux-kontext-pro"  # style change via prompt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

TMP_DIR = "tmp"
os.makedirs(TMP_DIR, exist_ok=True)

# token -> path to the downloaded photo (lives until the bot is restarted)
pending_photos: dict[str, str] = {}

# Popular styles for the "Change style" button
STYLES = {
    "anime": ("🌸 Аниме", "anime style, vibrant colors, cel shading, Studio Ghibli inspired art"),
    "watercolor": ("🎨 Акварель", "watercolor painting style, soft brush strokes, artistic paper texture"),
    "cyberpunk": ("🌆 Киберпанк", "cyberpunk style, neon lights, futuristic, high contrast, night city"),
    "oil": ("🖼 Масло", "oil painting style, classical fine art, textured brush strokes"),
    "pixar": ("🧸 3D мультфильм", "3d pixar cartoon style render, cute character, soft lighting"),
    "pixel": ("👾 Пиксель-арт", "pixel art style, 8-bit retro video game art"),
}


def main_menu_kb(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Апскейл", callback_data=f"m:u:{token}")],
            [InlineKeyboardButton(text="🗑 Удалить фон", callback_data=f"a:bg:{token}")],
            [InlineKeyboardButton(text="📝 Удалить текст", callback_data=f"a:tx:{token}")],
            [InlineKeyboardButton(text="🎨 Поменять стиль", callback_data=f"m:s:{token}")],
        ]
    )


def upscale_menu_kb(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="2x", callback_data=f"a:u2:{token}"),
                InlineKeyboardButton(text="4x", callback_data=f"a:u4:{token}"),
                InlineKeyboardButton(text="✨ Художественный", callback_data=f"a:ua:{token}"),
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"m:m:{token}")],
        ]
    )


def style_menu_kb(token: str) -> InlineKeyboardMarkup:
    keys = list(STYLES.keys())
    rows = []
    for i in range(0, len(keys), 2):
        row = []
        for key in keys[i : i + 2]:
            label, _ = STYLES[key]
            row.append(InlineKeyboardButton(text=label, callback_data=f"a:st:{key}:{token}"))
        rows.append(row)
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"m:m:{token}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "Привет! 👋\n\n"
        "Пришли мне фото, и я предложу, что с ним сделать:\n"
        "🔍 Апскейл — увеличение разрешения (на выбор: 2x, 4x или художественный)\n"
        "🗑 Удалить фон\n"
        "📝 Удалить текст\n"
        "🎨 Поменять стиль (на выбор — 6 популярных стилей)"
    )


@dp.message(F.photo)
async def handle_photo(message: Message):
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)

    token = uuid.uuid4().hex[:12]
    input_path = os.path.join(TMP_DIR, f"{token}.jpg")
    await bot.download_file(file.file_path, destination=input_path)
    pending_photos[token] = input_path

    await message.answer("Что сделать с этим фото?", reply_markup=main_menu_kb(token))


async def get_input_path(callback: CallbackQuery, token: str) -> str | None:
    path = pending_photos.get(token)
    if not path or not os.path.exists(path):
        await callback.answer("Фото больше не доступно, пришли его заново 🙏", show_alert=True)
        return None
    return path


@dp.callback_query(F.data.startswith("m:u:"))
async def cb_menu_upscale(callback: CallbackQuery):
    token = callback.data.split(":", 2)[2]
    await callback.message.edit_reply_markup(reply_markup=upscale_menu_kb(token))
    await callback.answer()


@dp.callback_query(F.data.startswith("m:s:"))
async def cb_menu_style(callback: CallbackQuery):
    token = callback.data.split(":", 2)[2]
    await callback.message.edit_reply_markup(reply_markup=style_menu_kb(token))
    await callback.answer()


@dp.callback_query(F.data.startswith("m:m:"))
async def cb_menu_main(callback: CallbackQuery):
    token = callback.data.split(":", 2)[2]
    await callback.message.edit_reply_markup(reply_markup=main_menu_kb(token))
    await callback.answer()


async def process_upscale(callback: CallbackQuery, token: str, label: str, runner):
    input_path = await get_input_path(callback, token)
    if not input_path:
        return
    await callback.answer()

    status_msg = await callback.message.answer(f"⏳ Делаю апскейл «{label}», подожди немного...")
    out_path = os.path.join(TMP_DIR, f"{token}_{uuid.uuid4().hex[:6]}.jpg")
    try:
        output_url = await runner(input_path)
        await download_result(output_url, out_path)
        await callback.message.answer_photo(FSInputFile(out_path), caption=f"✅ Апскейл {label} готов!")
    except Exception:
        logger.exception("Ошибка апскейла (%s)", label)
        await callback.message.answer(f"😔 Не получилось сделать апскейл «{label}». Попробуй ещё раз чуть позже.")
    finally:
        await status_msg.delete()
        if os.path.exists(out_path):
            os.remove(out_path)


@dp.callback_query(F.data.startswith("a:u2:"))
async def cb_upscale_2x(callback: CallbackQuery):
    token = callback.data.split(":", 2)[2]
    await process_upscale(callback, token, "2x", lambda p: run_upscale(p, 2))


@dp.callback_query(F.data.startswith("a:u4:"))
async def cb_upscale_4x(callback: CallbackQuery):
    token = callback.data.split(":", 2)[2]
    await process_upscale(callback, token, "4x", lambda p: run_upscale(p, 4))


@dp.callback_query(F.data.startswith("a:ua:"))
async def cb_upscale_artistic(callback: CallbackQuery):
    token = callback.data.split(":", 2)[2]
    await process_upscale(callback, token, "художественный", run_artistic_upscale)


@dp.callback_query(F.data.startswith("a:bg:"))
async def cb_remove_bg(callback: CallbackQuery):
    token = callback.data.split(":", 2)[2]
    input_path = await get_input_path(callback, token)
    if not input_path:
        return
    await callback.answer()

    status_msg = await callback.message.answer("⏳ Удаляю фон, подожди немного...")
    out_path = os.path.join(TMP_DIR, f"{token}_{uuid.uuid4().hex[:6]}.png")
    try:
        output_url = await run_remove_bg(input_path)
        await download_result(output_url, out_path)
        # send as a document, not a photo, to preserve PNG transparency
        await callback.message.answer_document(
            FSInputFile(out_path), caption="✅ Фон удалён (прозрачный PNG)."
        )
    except Exception:
        logger.exception("Ошибка при удалении фона")
        await callback.message.answer("😔 Не получилось удалить фон. Попробуй ещё раз чуть позже.")
    finally:
        await status_msg.delete()
        if os.path.exists(out_path):
            os.remove(out_path)


@dp.callback_query(F.data.startswith("a:tx:"))
async def cb_remove_text(callback: CallbackQuery):
    token = callback.data.split(":", 2)[2]
    input_path = await get_input_path(callback, token)
    if not input_path:
        return
    await callback.answer()

    status_msg = await callback.message.answer("⏳ Удаляю текст с фото, подожди немного...")
    out_path = os.path.join(TMP_DIR, f"{token}_{uuid.uuid4().hex[:6]}.png")
    try:
        output_url = await run_remove_text(input_path)
        await download_result(output_url, out_path)
        await callback.message.answer_photo(FSInputFile(out_path), caption="✅ Текст удалён.")
    except Exception:
        logger.exception("Ошибка при удалении текста")
        await callback.message.answer("😔 Не получилось удалить текст. Попробуй ещё раз чуть позже.")
    finally:
        await status_msg.delete()
        if os.path.exists(out_path):
            os.remove(out_path)


@dp.callback_query(F.data.startswith("a:st:"))
async def cb_style(callback: CallbackQuery):
    _, _, style_key, token = callback.data.split(":", 3)
    input_path = await get_input_path(callback, token)
    if not input_path:
        return
    label, prompt = STYLES[style_key]
    await callback.answer()

    status_msg = await callback.message.answer(f"⏳ Применяю стиль «{label}», подожди немного...")
    out_path = os.path.join(TMP_DIR, f"{token}_{uuid.uuid4().hex[:6]}.jpg")
    try:
        output_url = await run_edit(input_path, prompt)
        await download_result(output_url, out_path)
        await callback.message.answer_photo(FSInputFile(out_path), caption=f"✅ Стиль применён: {label}")
    except Exception:
        logger.exception("Ошибка при смене стиля")
        await callback.message.answer("😔 Не получилось поменять стиль. Попробуй ещё раз чуть позже.")
    finally:
        await status_msg.delete()
        if os.path.exists(out_path):
            os.remove(out_path)


async def run_upscale(input_path: str, scale: int) -> str:
    """Regular upscale via Real-ESRGAN (2x or 4x)."""

    def _call():
        with open(input_path, "rb") as f:
            output = replicate.run(
                UPSCALE_MODEL,
                input={
                    "image": f,
                    "scale": scale,
                    "face_enhance": False,
                },
            )
        return output

    output = await asyncio.to_thread(_call)
    return normalize_output_url(output)


async def run_artistic_upscale(input_path: str) -> str:
    """Artistic upscale (diffusion-based, with detail enhancement) via Clarity Upscaler."""

    def _call():
        with open(input_path, "rb") as f:
            output = replicate.run(
                ARTISTIC_UPSCALE_MODEL,
                input={
                    "image": f,
                    "scale_factor": 2,
                    "creativity": 0.4,
                    "dynamic": 6,
                    "resemblance": 0.6,
                },
            )
        return output

    output = await asyncio.to_thread(_call)
    return normalize_output_url(output)


async def run_remove_bg(input_path: str) -> str:
    def _call():
        with open(input_path, "rb") as f:
            output = replicate.run(
                BG_REMOVE_MODEL,
                input={"image": f},
            )
        return output

    output = await asyncio.to_thread(_call)
    return normalize_output_url(output)


async def run_remove_text(input_path: str) -> str:
    def _call():
        with open(input_path, "rb") as f:
            output = replicate.run(
                TEXT_REMOVE_MODEL,
                input={"input_image": f},
            )
        return output

    output = await asyncio.to_thread(_call)
    return normalize_output_url(output)


async def run_edit(input_path: str, prompt: str) -> str:
    """Prompt-based edits (style change) via FLUX.1 Kontext."""

    def _call():
        with open(input_path, "rb") as f:
            output = replicate.run(
                EDIT_MODEL,
                input={
                    "input_image": f,
                    "prompt": prompt,
                    "output_format": "jpg",
                },
            )
        return output

    output = await asyncio.to_thread(_call)
    return normalize_output_url(output)


def normalize_output_url(output) -> str:
    """
    Different versions of the replicate SDK and different models return the result differently:
    - a plain string with the URL
    - a FileOutput object (has a .url attribute, or itself converts to str)
    - a list of one or more elements of any of the types above
    This function always extracts a clean URL string from it.
    """
    # if a list/tuple came back — take the first element
    if isinstance(output, (list, tuple)):
        if not output:
            raise ValueError("Model returned an empty result")
        output = output[0]

    # in newer SDK versions, the FileOutput object has a url method/attribute
    if hasattr(output, "url"):
        url = output.url
        return url() if callable(url) else url

    # in case the object just converts nicely to a string (the URL itself)
    return str(output)


async def download_result(url: str, output_path: str):
    import aiohttp

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            data = await resp.read()
            with open(output_path, "wb") as f:
                f.write(data)


@dp.message(F.document)
async def handle_document_photo(message: Message):
    # if the user sent the photo as an uncompressed file, guide them too
    if message.document.mime_type and message.document.mime_type.startswith("image/"):
        await message.answer(
            "Пришли фото как обычное изображение (не файлом), "
            "тогда я смогу его обработать 🙂"
        )


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
