import os
import asyncio
import subprocess
import textwrap
import logging
from gtts import gTTS
from PIL import Image, ImageDraw, ImageFont
from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    filters,
    ContextTypes,
)

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")

# Paths
HINDI_FONT = "/usr/share/fonts/truetype/noto-hindi.ttf"
FALLBACK_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
OUTPUT_DIR = "/tmp/videobot"


def get_font(size):
    """Font load करें — Hindi पहले, नहीं तो default"""
    for font_path in [HINDI_FONT, FALLBACK_FONT]:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def wrap_text(text, max_chars=22):
    """Text को lines में तोड़ें"""
    return textwrap.wrap(text, width=max_chars)


def create_slide(text, slide_num, total, out_path):
    """एक slide/image बनाएं"""
    W, H = 1280, 720

    # Background gradient effect
    img = Image.new("RGB", (W, H), color=(10, 10, 40))
    draw = ImageDraw.Draw(img)

    # Background design
    for i in range(H):
        ratio = i / H
        r = int(10 + 30 * ratio)
        g = int(10 + 10 * ratio)
        b = int(40 + 60 * ratio)
        draw.line([(0, i), (W, i)], fill=(r, g, b))

    # Border
    draw.rectangle([15, 15, W - 15, H - 15], outline=(255, 200, 0), width=3)
    draw.rectangle([20, 20, W - 20, H - 20], outline=(255, 200, 0, 100), width=1)

    # Slide number
    small_font = get_font(28)
    draw.text(
        (W // 2, 50),
        f"{slide_num} / {total}",
        font=small_font,
        fill=(180, 180, 180),
        anchor="mm",
    )

    # Main text
    main_font = get_font(62)
    lines = wrap_text(text, max_chars=22)

    total_height = len(lines) * 80
    y_start = (H - total_height) // 2

    for i, line in enumerate(lines):
        y = y_start + i * 80

        # Shadow effect
        draw.text((W // 2 + 2, y + 2), line, font=main_font,
                  fill=(0, 0, 0), anchor="mm")
        # Main text
        draw.text((W // 2, y), line, font=main_font,
                  fill=(255, 255, 255), anchor="mm")

    # Bottom decoration line
    draw.line([(100, H - 60), (W - 100, H - 60)], fill=(255, 200, 0), width=2)

    img.save(out_path, "PNG")


def split_script(script):
    """Script को meaningful parts में तोड़ें"""
    import re

    # पहले sentences तोड़ें
    parts = re.split(r'[।\.!\?]+', script)
    parts = [p.strip() for p in parts if p.strip() and len(p.strip()) > 2]

    # बहुत लंबे parts को और तोड़ें
    final_parts = []
    for part in parts:
        if len(part) > 60:
            sub = textwrap.wrap(part, width=55)
            final_parts.extend(sub)
        else:
            final_parts.append(part)

    return final_parts if final_parts else [script]


def create_video(script_text, job_id):
    """पूरी video बनाएं"""
    job_dir = os.path.join(OUTPUT_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    # 1. Audio बनाएं
    logger.info(f"[{job_id}] Audio बन रही है...")
    audio_path = os.path.join(job_dir, "audio.mp3")
    tts = gTTS(text=script_text, lang="hi", slow=False)
    tts.save(audio_path)

    # 2. Script को parts में तोड़ें
    parts = split_script(script_text)
    logger.info(f"[{job_id}] {len(parts)} slides बनेंगी")

    # 3. हर part की image बनाएं
    image_files = []
    for i, part in enumerate(parts):
        img_path = os.path.join(job_dir, f"slide_{i:04d}.png")
        create_slide(part, i + 1, len(parts), img_path)
        image_files.append(img_path)

    # 4. Images से video बनाएं
    logger.info(f"[{job_id}] Images से video बन रही है...")
    concat_file = os.path.join(job_dir, "concat.txt")
    
    # Audio duration निकालें
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
        capture_output=True, text=True
    )
    
    try:
        audio_duration = float(result.stdout.strip())
    except Exception:
        audio_duration = len(parts) * 4.0

    # हर slide को equal time दें
    slide_duration = audio_duration / len(parts)
    slide_duration = max(slide_duration, 2.0)  # कम से कम 2 seconds

    with open(concat_file, "w") as f:
        for img_path in image_files:
            f.write(f"file '{img_path}'\n")
            f.write(f"duration {slide_duration:.2f}\n")
        # Last frame repeat (ffmpeg requirement)
        f.write(f"file '{image_files[-1]}'\n")

    video_only = os.path.join(job_dir, "video_only.mp4")
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_file,
            "-vf", "fps=24,scale=1280:720,format=yuv420p",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            video_only,
        ],
        capture_output=True,
        check=True,
    )

    # 5. Audio + Video merge करें
    logger.info(f"[{job_id}] Audio और Video जोड़ी जा रही है...")
    final_video = os.path.join(job_dir, "final_video.mp4")
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", video_only,
            "-i", audio_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            final_video,
        ],
        capture_output=True,
        check=True,
    )

    logger.info(f"[{job_id}] Video तैयार!")
    return final_video


def cleanup(job_id):
    """Files delete करें"""
    import shutil
    job_dir = os.path.join(OUTPUT_DIR, job_id)
    if os.path.exists(job_dir):
        shutil.rmtree(job_dir)


# === Telegram Handlers ===

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 नमस्ते! मैं Script-to-Video Bot हूँ।\n\n"
        "📝 मुझे कोई भी script भेजें\n"
        "🎙️ मैं उसकी आवाज़ बनाऊँगा\n"
        "🎥 और पूरी video बनाकर दूँगा!\n\n"
        "बस अभी कोई script लिखकर भेजें 👇"
    )


async def handle_script(update: Update, context: ContextTypes.DEFAULT_TYPE):
    script = update.message.text.strip()
    user_id = update.effective_user.id
    job_id = f"job_{user_id}_{update.message.message_id}"

    # Validation
    if len(script) < 15:
        await update.message.reply_text(
            "⚠️ Script बहुत छोटी है!\nकम से कम एक पूरा sentence लिखें।"
        )
        return

    if len(script) > 3000:
        await update.message.reply_text(
            "⚠️ Script बहुत लंबी है!\n3000 characters से कम रखें।"
        )
        return

    msg = await update.message.reply_text(
        "⏳ आपकी video बन रही है...\n"
        "🎙️ Audio तैयार हो रही है\n"
        "🖼️ Slides बन रही हैं\n"
        "🎬 Video render हो रही है\n\n"
        "2-3 मिनट का इंतज़ार करें..."
    )

    try:
        # Video बनाएं
        video_path = await asyncio.get_event_loop().run_in_executor(
            None, create_video, script, job_id
        )

        # Video भेजें
        await msg.delete()
        with open(video_path, "rb") as v:
            await update.message.reply_video(
                video=v,
                caption=(
                    "✅ आपकी Video तैयार है!\n\n"
                    "📝 Script से Video बनाई गई\n"
                    "🎙️ Hindi Audio शामिल है\n\n"
                    "नई video के लिए कोई और script भेजें!"
                ),
                supports_streaming=True,
            )

    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg error: {e.stderr}")
        await msg.edit_text(
            "❌ Video बनाने में error आई!\n"
            "कृपया दोबारा try करें।"
        )
    except Exception as e:
        logger.error(f"Error: {e}")
        await msg.edit_text(
            "❌ कुछ गड़बड़ हो गई!\n"
            "दोबारा script भेजें।"
        )
    finally:
        cleanup(job_id)


def main():
    if not TOKEN:
        raise ValueError("BOT_TOKEN environment variable नहीं मिला!")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_script))

    logger.info("✅ Bot चालू हो गया!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
