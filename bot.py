import os
import asyncio
import subprocess
import textwrap
import logging
import requests
import random
from gtts import gTTS
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")
UNSPLASH_KEY = os.environ.get("UNSPLASH_KEY")
HINDI_FONT = "/usr/share/fonts/truetype/noto-hindi.ttf"
FALLBACK_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
OUTPUT_DIR = "/tmp/videobot"

MUSIC_LIST = [
    "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
    "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3",
    "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3",
]


def get_font(size):
    for font_path in [HINDI_FONT, FALLBACK_FONT]:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def get_keywords(script):
    stop_words = {
        "है", "हैं", "का", "की", "के", "में", "और", "को", "से", "पर",
        "यह", "वह", "जो", "कि", "एक", "हम", "आप", "वे", "इस", "उस",
        "भी", "तो", "ही", "नहीं", "जब", "तक", "अब", "था", "थी", "थे",
        "होता", "होती", "होते", "किया", "करना", "करते", "लिए", "बहुत",
        "अपने", "अपनी", "हमारे", "आज", "कल", "यहाँ", "वहाँ", "कैसे",
        "क्या", "क्यों", "कौन", "कहाँ", "जैसे", "ऐसे", "बारे", "बात"
    }
    hindi_to_english = {
        "भारत": "India", "देश": "country India", "इतिहास": "history ancient",
        "प्रकृति": "nature", "पानी": "water river", "पहाड़": "mountain",
        "जंगल": "forest", "आकाश": "sky clouds", "सूरज": "sunrise sunset",
        "रात": "night stars", "शहर": "city urban", "गाँव": "village rural",
        "खेत": "farm field", "फूल": "flowers", "पेड़": "trees forest",
        "समुद्र": "ocean sea", "नदी": "river", "विज्ञान": "science technology",
        "शिक्षा": "education school", "स्वास्थ्य": "health wellness",
        "खेल": "sports", "संगीत": "music", "कला": "art",
        "व्यापार": "business", "तकनीक": "technology", "अंतरिक्ष": "space universe",
        "युद्ध": "war history", "शांति": "peace", "धर्म": "religion temple",
        "परिवार": "family", "बच्चे": "children", "सफलता": "success motivation",
        "जीवन": "life journey",
    }
    words = script.replace('।', ' ').replace(',', ' ').split()
    english_keywords = []
    for word in words:
        if word in hindi_to_english:
            english_keywords.append(hindi_to_english[word])
    if not english_keywords:
        english_keywords = ["beautiful landscape india"]
    return english_keywords[0]


def download_background(keyword, job_dir):
    try:
        url = "https://api.unsplash.com/photos/random"
        params = {"query": keyword, "orientation": "landscape", "client_id": UNSPLASH_KEY}
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            img_url = data["urls"]["regular"]
            img_response = requests.get(img_url, timeout=15)
            if img_response.status_code == 200:
                img_path = os.path.join(job_dir, "background.jpg")
                with open(img_path, "wb") as f:
                    f.write(img_response.content)
                return img_path
    except Exception as e:
        logger.error(f"Image download error: {e}")
    return None


def download_music(job_dir):
    try:
        music_url = random.choice(MUSIC_LIST)
        music_path = os.path.join(job_dir, "music.mp3")
        response = requests.get(music_url, timeout=20)
        if response.status_code == 200:
            with open(music_path, "wb") as f:
                f.write(response.content)
            return music_path
    except Exception as e:
        logger.error(f"Music download error: {e}")
    return None


def create_frame(bg_path, words_so_far, all_words, frame_num, job_dir):
    W, H = 1280, 720
    if bg_path and os.path.exists(bg_path):
        img = Image.open(bg_path).convert("RGB")
        img = img.resize((W, H), Image.LANCZOS)
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(0.45)
        img = img.filter(ImageFilter.GaussianBlur(radius=1.5))
    else:
        img = Image.new("RGB", (W, H), color=(10, 10, 30))

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    for i in range(H // 2, H):
        alpha = int(180 * (i - H // 2) / (H // 2))
        overlay_draw.line([(0, i), (W, i)], fill=(0, 0, 0, alpha))
    img = img.convert("RGBA")
    img = Image.alpha_composite(img, overlay)
    img = img.convert("RGB")
    draw = ImageDraw.Draw(img)

    current_text = " ".join(words_so_far)
    main_font = get_font(58)
    lines = textwrap.wrap(current_text, width=25)
    if len(lines) > 3:
        lines = lines[-3:]

    total_h = len(lines) * 75
    y_start = H - total_h - 80

    for i, line in enumerate(lines):
        y = y_start + i * 75
        is_last = (i == len(lines) - 1)
        draw.text((W // 2 + 2, y + 2), line, font=main_font, fill=(0, 0, 0), anchor="mm")
        color = (255, 230, 0) if is_last else (255, 255, 255)
        draw.text((W // 2, y), line, font=main_font, fill=color, anchor="mm")

    progress = len(words_so_far) / max(len(all_words), 1)
    bar_w = int((W - 100) * progress)
    draw.rectangle([50, H - 25, W - 50, H - 15], fill=(80, 80, 80))
    draw.rectangle([50, H - 25, 50 + bar_w, H - 15], fill=(255, 200, 0))

    frame_path = os.path.join(job_dir, f"frame_{frame_num:06d}.png")
    img.save(frame_path, "PNG")
    return frame_path


def create_video(script_text, job_id):
    job_dir = os.path.join(OUTPUT_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    logger.info(f"[{job_id}] Audio बन रही है...")
    audio_path = os.path.join(job_dir, "voice.mp3")
    tts = gTTS(text=script_text, lang="hi", slow=False)
    tts.save(audio_path)

    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
        capture_output=True, text=True
    )
    try:
        audio_duration = float(result.stdout.strip())
    except Exception:
        audio_duration = 30.0

    logger.info(f"[{job_id}] Background image download हो रही है...")
    keyword = get_keywords(script_text)
    bg_path = download_background(keyword, job_dir)

    logger.info(f"[{job_id}] Music download हो रही है...")
    music_path = download_music(job_dir)

    logger.info(f"[{job_id}] Frames बन रहे हैं...")
    words = script_text.replace('।', ' । ').split()
    words = [w for w in words if w.strip()]

    fps = 24
    total_frames = int(audio_duration * fps)
    frames_per_word = max(1, total_frames // max(len(words), 1))

    frame_files = []
    frame_num = 0

    for word_idx in range(len(words)):
        words_so_far = words[:word_idx + 1]
        for f in range(frames_per_word):
            frame_path = create_frame(bg_path, words_so_far, words, frame_num, job_dir)
            frame_files.append(frame_path)
            frame_num += 1

    while frame_num < total_frames:
        frame_path = create_frame(bg_path, words, words, frame_num, job_dir)
        frame_files.append(frame_path)
        frame_num += 1

    logger.info(f"[{job_id}] Video render हो रही है...")
    frames_list = os.path.join(job_dir, "frames.txt")
    with open(frames_list, "w") as f:
        for fp in frame_files:
            f.write(f"file '{fp}'\n")
            f.write(f"duration {1/fps:.4f}\n")
        f.write(f"file '{frame_files[-1]}'\n")

    video_silent = os.path.join(job_dir, "video_silent.mp4")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", frames_list,
        "-vf", f"fps={fps},scale=1280:720,format=yuv420p",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        video_silent,
    ], capture_output=True, check=True)

    final_video = os.path.join(job_dir, "final_video.mp4")

    if music_path and os.path.exists(music_path):
        mixed_audio = os.path.join(job_dir, "mixed_audio.aac")
        subprocess.run([
            "ffmpeg", "-y",
            "-i", audio_path,
            "-i", music_path,
            "-filter_complex",
            f"[0:a]volume=1.8[voice];[1:a]volume=0.15,atrim=0:{audio_duration}[music];[voice][music]amix=inputs=2:duration=first[aout]",
            "-map", "[aout]",
            "-c:a", "aac", "-b:a", "192k",
            mixed_audio,
        ], capture_output=True, check=True)

        subprocess.run([
            "ffmpeg", "-y",
            "-i", video_silent,
            "-i", mixed_audio,
            "-c:v", "copy", "-c:a", "copy",
            "-shortest", final_video,
        ], capture_output=True, check=True)
    else:
        subprocess.run([
            "ffmpeg", "-y",
            "-i", video_silent,
            "-i", audio_path,
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", final_video,
        ], capture_output=True, check=True)

    logger.info(f"[{job_id}] Video तैयार!")
    return final_video


def cleanup(job_id):
    import shutil
    job_dir = os.path.join(OUTPUT_DIR, job_id)
    if os.path.exists(job_dir):
        shutil.rmtree(job_dir)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 नमस्ते! मैं Script-to-Video Bot हूँ!\n\n"
        "✨ मैं बनाऊँगा:\n"
        "🖼️ Script से matching background\n"
        "⌨️ Typewriter style text\n"
        "🎵 Background music\n"
        "🎙️ Hindi voice over\n\n"
        "📝 अभी कोई Hindi script भेजें! 👇"
    )


async def handle_script(update: Update, context: ContextTypes.DEFAULT_TYPE):
    script = update.message.text.strip()
    user_id = update.effective_user.id
    job_id = f"job_{user_id}_{update.message.message_id}"

    if len(script) < 15:
        await update.message.reply_text("⚠️ Script बहुत छोटी है!")
        return

    if len(script) > 2000:
        await update.message.reply_text("⚠️ 2000 characters से कम लिखें!")
        return

    msg = await update.message.reply_text(
        "🎬 Video बन रही है...\n"
        "⏳ 3-5 मिनट लगेंगे, इंतज़ार करें..."
    )

    try:
        video_path = await asyncio.get_event_loop().run_in_executor(
            None, create_video, script, job_id
        )
        await msg.delete()
        with open(video_path, "rb") as v:
            await update.message.reply_video(
                video=v,
                caption="✅ Video तैयार है! नई video के लिए नई script भेजें! 🎬",
                supports_streaming=True,
            )
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg error: {e}")
        await msg.edit_text("❌ Video बनाने में error! दोबारा try करें।")
    except Exception as e:
        logger.error(f"Error: {e}")
        await msg.edit_text("❌ कुछ गड़बड़ हो गई! दोबारा script भेजें।")
    finally:
        cleanup(job_id)


def main():
    if not TOKEN:
        raise ValueError("BOT_TOKEN नहीं मिला!")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_script))
    logger.info("✅ Bot चालू हो गया!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
