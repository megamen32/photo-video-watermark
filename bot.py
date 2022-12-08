import traceback

import settings
import aiogram
from aiogram.types import InlineKeyboardMarkup ,InlineKeyboardButton
from aiogram.dispatcher import FSMContext
import logging
import datetime
import os
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from colorthief import ColorThief
import asyncio
import aiohttp

from watermark import Watermark, File, apply_watermark

work_directory = os.path.dirname(os.path.abspath(__file__))
downloads_directory = '/tmp/photo-video-watermark/downloads'
# Create directories if not exists
if not os.path.exists(downloads_directory):
    os.makedirs(downloads_directory)
if not os.path.exists(downloads_directory + '/videos'):
    os.makedirs(downloads_directory + '/videos')
if not os.path.exists(downloads_directory + '/photos'):
    os.makedirs(downloads_directory + '/photos')

logging.basicConfig(level=logging.INFO)
from aiogram.contrib.fsm_storage.memory import MemoryStorage

storage = MemoryStorage()
bot = aiogram.Bot(token=settings.bot['token'])

dp = aiogram.Dispatcher(bot,storage=storage)


class IsAllowedUser(aiogram.dispatcher.filters.BoundFilter):
    key = 'is_allowed_user'  # Use is_allowed_user=True in aiogram Dispather for check user permission to use this function via bot implementations

    def __init__(self, is_allowed_user):
        self.is_allowed_user = is_allowed_user

    async def check(self, message: aiogram.types.Message):
        user = message.from_user.id
        if user in settings.bot['allowed_users']:
            return True
        else:
            return False


dp.filters_factory.bind(IsAllowedUser)  # Register custom filter


@dp.message_handler(commands=['start'])
async def start(message: aiogram.types.Message):
    await bot.set_my_commands([
        aiogram.types.BotCommand('/settings','set settings for watermark'),
        aiogram.types.BotCommand('/set','set watermark image')
                               ])
    await message.answer("Hi. It's watermark bot.\nType /help for details.")


@dp.message_handler(commands=['help'])
async def help(message: aiogram.types.Message):
    if len(message.text.split(' ')) == 1:
        await message.answer(settings.help['help_info'])
    else:
        params = message.text.split(' ')
        if params[1] == 'photo':
            await message.answer(settings.help['photo_help_answer'])
        elif params[1] == 'video':
            await message.answer('video help')
        elif params[1] == 'link':
            await message.answer('link help')


async def AnalyzeWatermarkColor(photo_abspath, pos, size):
    photo = Image.open(photo_abspath).copy().convert("RGB").crop((pos[0], pos[1], pos[0] + size[0], pos[1] + size[1]))
    photo.save(photo_abspath)
    img = ColorThief(photo_abspath)
    dominant_color = img.get_color()
    d = 0
    luminance = (0.299 * dominant_color[0] + 0.587 * dominant_color[1] + 0.114 * dominant_color[2]) / 255
    il = float(str(luminance)[0:3])
    if il == 0.1:
        d = 230
    elif il == 0.2:
        d = 210
    elif il == 0.3:
        d = 190
    elif il == 0.4:
        d = 170
    elif il == 0.5:
        d = 150
    elif il == 0.6:
        d = 130
    elif il == 0.7:
        d = 110
    elif il == 0.8:
        d = 90
    elif il == 0.9:
        d = 70
    user_text_fill = (d, d, d, 220)
    return user_text_fill


async def PhotoWatermark(photo_abspath, user_text_fill, user_input):
    photo = Image.open(photo_abspath)
    with BytesIO() as f:
        photo.save(f, format='PNG')
        photo = Image.open(f).convert("RGBA")
        f.close()
        text = settings.watermark['watermark_default_text']

        photo_width, photo_height = photo.size
        txt = Image.new("RGBA", photo.size, (255, 255, 255, 0))

        photo_min_side = photo_width if photo_width < photo_height else photo_height
        font_size = photo_min_side // 14
        font = ImageFont.truetype("{}/fonts/{}".format(work_directory, "Hack-Bold.ttf"), font_size)
        draw = ImageDraw.Draw(txt)

        text_width, text_height = draw.textsize(text, font)
        margin_x = photo_width // 55
        margin_y = photo_height // 60
        x = photo_width - text_width - margin_x
        y = photo_height - text_height - margin_y
        pos = (x, y)

        text_fill = user_text_fill
        if user_input == False:
            text_fill = await AnalyzeWatermarkColor(photo_abspath, pos, (text_width, text_height))
        text_stroke_fill = text_fill
        draw.text(pos, text, fill=text_fill, font=font, stroke_fill=text_stroke_fill)
        photo_outpath = str(*photo_abspath.split('.')[:-1]) + '_edited.png'  # Creat same photo in .png format

        combined = Image.alpha_composite(photo, txt)
        combined.save(photo_outpath)
        return photo_outpath


@dp.message_handler(commands='set')
async def InitWatermarkSet(message: aiogram.types.Message, state: FSMContext):
    await message.answer('Send watermark logo')
    await state.set_state('settings')

@dp.message_handler( state='settings')
async def WatermarkSetInvalid(message: aiogram.types.Message, state: FSMContext):
    if 'cancel' in message.text:
        await state.reset_state()
        return await message.answer('canceled')

    await message.answer('Send photo')
@dp.message_handler(content_types=aiogram.types.ContentType.PHOTO,  state='settings')
async def WatermarkSet(message: aiogram.types.Message, state: FSMContext):
    photo_abspath = '{}/photos/{}.jpg'.format(downloads_directory, datetime.datetime.now().strftime(
        "%Y%m%d-%H%M%S-%f"))  # Downloaded photo path to downloads/photos
    await state.finish()
    # Download photo
    file_id = message.photo[-1].file_id
    file = await bot.get_file(file_id)
    file_path = file.file_path
    await bot.download_file(file_path, photo_abspath)

    # Work with photo
    settings.watermark['watermark'] = photo_abspath
    await message.reply(f'watermark_set to {photo_abspath}')


@dp.message_handler(commands='settings')
async def InitWatermarkSet(message: aiogram.types.Message, state: FSMContext):
    position_tag = None
    data=await get_wtm_settings(message.chat.id,message.from_user.id)
    watermark_position = data['watermark_position']
    if watermark_position == "5:main_h-overlay_h":
        position_tag = "Bottom Left"
    elif watermark_position == "main_w-overlay_w-5:main_h-overlay_h-5":
        position_tag = "Bottom Right"
    elif watermark_position == "main_w-overlay_w-5:5":
        position_tag = "Top Right"
    elif watermark_position == "5:5":
        position_tag = "Top Left"

    watermark_size = data['watermark_size']
    if int(watermark_size) == 5:
        size_tag = "5%"
    elif int(watermark_size) == 7:
        size_tag = "7%"
    elif int(watermark_size) == 10:
        size_tag = "10%"
    elif int(watermark_size) == 15:
        size_tag = "15%"
    elif int(watermark_size) == 20:
        size_tag = "20%"
    elif int(watermark_size) == 25:
        size_tag = "25%"
    elif int(watermark_size) == 30:
        size_tag = "30%"
    elif int(watermark_size) == 35:
        size_tag = "35%"
    elif int(watermark_size) == 40:
        size_tag = "40%"
    elif int(watermark_size) == 45:
        size_tag = "45%"
    else:
        size_tag = "7%"
    ## --- Next --- ##
    try:
        keyboard_markup = InlineKeyboardMarkup()

        btns=[[InlineKeyboardButton(f"Watermark Position - {position_tag}", callback_data="lol")],
         [InlineKeyboardButton("Set Top Left", callback_data=f"position_5:5"),
          InlineKeyboardButton("Set Top Right", callback_data=f"position_main_w-overlay_w-5:5")],
         [InlineKeyboardButton("Set Bottom Left", callback_data=f"position_5:main_h-overlay_h"),
          InlineKeyboardButton("Set Bottom Right",
                               callback_data=f"position_main_w-overlay_w-5:main_h-overlay_h-5")],
         [InlineKeyboardButton(f"Watermark Size - {size_tag}", callback_data="lel")],
         [InlineKeyboardButton("5%", callback_data=f"size_5"), InlineKeyboardButton("7%", callback_data=f"size_7"),
          InlineKeyboardButton("10%", callback_data=f"size_10"),
          InlineKeyboardButton("15%", callback_data=f"size_15"),
          InlineKeyboardButton("20%", callback_data=f"size_20")],
         [InlineKeyboardButton("25%", callback_data=f"size_25"),
          InlineKeyboardButton("30%", callback_data=f"size_30"),
          InlineKeyboardButton("35%", callback_data=f"size_30"),
          InlineKeyboardButton("40%", callback_data=f"size_40"),
          InlineKeyboardButton("45%", callback_data=f"size_45")],
         [InlineKeyboardButton(f"Reset Settings To Default", callback_data="reset")]]
        for arr in btns:
            keyboard_markup.row(*arr)

        await message.reply(
            text="Here you can set your Watermark Settings:",
            disable_web_page_preview=True,
            parse_mode="Markdown",
            reply_markup=keyboard_markup
        )
        print('settings')
    except:traceback.print_exc()
@dp.callback_query_handler(state='*')
async def callb_hander(query:aiogram.types.CallbackQuery):
    cb_data=query.data
    data = await get_wtm_settings(query.message.chat.id,query.from_user.id)

    if cb_data.startswith("position_") or cb_data.startswith("size_"):

        new_position = cb_data.split("_", 1)[1]
        if cb_data.startswith("position_"):
            await dp.storage.update_data(chat=query.message.chat.id,user=query.from_user.id, watermark_position=new_position,watermark_size=data['watermark_size'])

        elif cb_data.startswith("size_"):
            await dp.storage.update_data(chat=query.message.chat.id, user=query.from_user.id,
                                         watermark_size=new_position,watermark_position=data['watermark_position'])
    data = await get_wtm_settings(chat=query.message.chat.id, user=query.from_user.id)
    watermark_position = data['watermark_position']
    if watermark_position == "5:main_h-overlay_h":
        position_tag = "Bottom Left"
    elif watermark_position == "main_w-overlay_w-5:main_h-overlay_h-5":
        position_tag = "Bottom Right"
    elif watermark_position == "main_w-overlay_w-5:5":
        position_tag = "Top Right"
    elif watermark_position == "5:5":
        position_tag = "Top Left"
    else:
        position_tag = "Top Left"

    watermark_size = data['watermark_size']
    if int(watermark_size) == 5:
        size_tag = "5%"
    elif int(watermark_size) == 7:
        size_tag = "7%"
    elif int(watermark_size) == 10:
        size_tag = "10%"
    elif int(watermark_size) == 15:
        size_tag = "15%"
    elif int(watermark_size) == 20:
        size_tag = "20%"
    elif int(watermark_size) == 25:
        size_tag = "25%"
    elif int(watermark_size) == 30:
        size_tag = "30%"
    elif int(watermark_size) == 35:
        size_tag = "35%"
    elif int(watermark_size) == 40:
        size_tag = "40%"
    elif int(watermark_size) == 45:
        size_tag = "45%"
    else:
        size_tag = "7%"
    try:
        keyboard_markup = InlineKeyboardMarkup()
        btns=            [[InlineKeyboardButton(f"Watermark Position - {position_tag}", callback_data="lol")],
             [InlineKeyboardButton("Set Top Left", callback_data=f"position_5:5"),
              InlineKeyboardButton("Set Top Right", callback_data=f"position_main_w-overlay_w-5:5")],
             [InlineKeyboardButton("Set Bottom Left", callback_data=f"position_5:main_h-overlay_h"),
              InlineKeyboardButton("Set Bottom Right",
                                   callback_data=f"position_main_w-overlay_w-5:main_h-overlay_h-5")],
             [InlineKeyboardButton(f"Watermark Size - {size_tag}", callback_data="lel")],
             [InlineKeyboardButton("5%", callback_data=f"size_5"), InlineKeyboardButton("7%", callback_data=f"size_7"),
              InlineKeyboardButton("10%", callback_data=f"size_10"),
              InlineKeyboardButton("15%", callback_data=f"size_15"),
              InlineKeyboardButton("20%", callback_data=f"size_20")],
             [InlineKeyboardButton("25%", callback_data=f"size_25"),
              InlineKeyboardButton("30%", callback_data=f"size_30"),
              InlineKeyboardButton("35%", callback_data=f"size_30"),
              InlineKeyboardButton("40%", callback_data=f"size_40"),
              InlineKeyboardButton("45%", callback_data=f"size_45")],
             [InlineKeyboardButton(f"Reset Settings To Default", callback_data="reset")]]
        for row in btns:
            keyboard_markup.row(*row)
        await query.message.edit_text(
            text="Here you can set your Watermark Settings:",
            disable_web_page_preview=True,
            parse_mode="Markdown",
            reply_markup=keyboard_markup
        )
    except aiogram.exceptions.MessageNotModified:
        pass

@dp.message_handler(content_types=aiogram.types.ContentType.PHOTO)
async def PhotoProcess(message: aiogram.types.Message):
    photo_abspath = '{}/photos/{}.jpg'.format(downloads_directory, datetime.datetime.now().strftime(
        "%Y%m%d-%H%M%S-%f"))  # Downloaded photo path to downloads/photos

    # Download photo
    file_id = message.photo[-1].file_id
    file = await bot.get_file(file_id)
    file_path = file.file_path
    await bot.download_file(file_path, photo_abspath)

    # Work with photo
    data= await get_wtm_settings(message.chat.id,message.from_user.id)
    watermark_position=data['watermark_position']
    if watermark_position == "5:main_h-overlay_h":
        position_tag = "bottom_left"
    elif watermark_position == "main_w-overlay_w-5:main_h-overlay_h-5":
        position_tag = "bottom_right"
    elif watermark_position == "main_w-overlay_w-5:5":
        position_tag = "top_right"
    elif watermark_position == "5:5":
        position_tag = "top_left"
    else:
        position_tag = "top_left"
    watermark_size = data['watermark_size']
    wtm = Watermark(File(settings.watermark['watermark']), watermark_position,size=watermark_size)
    photo_abspath2 = '{}/photos/{}_edit.jpg'.format(downloads_directory, datetime.datetime.now().strftime(
        "%Y%m%d-%H%M%S-%f"))  # Downloaded photo path to downloads/photos

    photo_outpath = apply_watermark(File(photo_abspath), wtm, frame_rate=30, output_file=photo_abspath2)
    # Send photo
    await message.answer_photo(aiogram.types.InputFile(photo_outpath))
    logging.info('[PHOTO] - [{}] - Watermark has been successfully inserted to photo {} owned user {}.'.format(
        datetime.datetime.now().strftime("%H:%M:%S-%d.%m.%Y"), file_id, message.from_user.id))
    os.remove(photo_abspath)  # Delete .jpg
    os.remove(photo_outpath)  # Delete .png


async def get_wtm_settings(chat,user):
    data= await dp.storage.get_data(chat=chat, user=user)
    if 'watermark_position' not in data:
        data['watermark_position'] = '5:5'
    if 'watermark_size' not in data:
        data['watermark_size'] = '5'
    return data


@dp.message_handler(content_types=aiogram.types.ContentType.VIDEO)
async def VideoProcess(message: aiogram.types.Message):
    video_abspath = '{}/videos/{}.mp4'.format(downloads_directory, datetime.datetime.now().strftime(
        "%Y%m%d-%H%M%S-%f"))  # Downloaded video path to downloads/video
    watermark_abspath = settings.watermark['watermark']

    # Download video
    file_id = message.video.file_id
    file = await bot.get_file(file_id)
    file_path = file.file_path
    await bot.download_file(file_path, video_abspath)

    # Work with video
    video_edited_abspath = str(*video_abspath.split('.')[:-1]) + '_edited.mp4'
    data=await get_wtm_settings(chat=message.chat.id,user=message.from_user.id)
    watermark_size = data['watermark_size']
    watermark_position = data['watermark_position']
    wtm = Watermark(File(settings.watermark['watermark']), watermark_position, size=watermark_size)


    video_edited_abspath = apply_watermark(File(video_abspath), wtm, frame_rate=30, output_file=video_edited_abspath)

    # Send video
    await message.answer_video(aiogram.types.InputFile(video_edited_abspath), caption="")
    logging.info(
        '[VIDEO] - [{}] - Video {} has been converted from user {}. And watermark has been successfully inserted into the video.'.format(
            datetime.datetime.now().strftime("%H:%M:%S-%d.%m.%Y"), file_id, message.from_user.id))

    os.remove(video_abspath)
    os.remove(video_edited_abspath)


async def LinkPhotoProcess(message, link):
    photo_abspath = '{}/photos/{}.png'.format(downloads_directory, datetime.datetime.now().strftime(
        "%Y%m%d-%H%M%S-%f"))  # Downloaded photo path to downloads/photos
    # Download photo in jpg or png format
    async with aiohttp.ClientSession() as session:
        async with session.get(link, allow_redirects=True) as response:
            # Download photo
            assert response.status == 200
            photo_bytes = await response.read()
            photo = Image.open(BytesIO(photo_bytes))
            photo.save(photo_abspath)

            # Work with photo
            photo_outpath = await PhotoWatermark(photo_abspath, user_text_fill="", user_input=False)

            # Send photo
            await message.answer_photo(aiogram.types.InputFile(photo_outpath), caption="")
            logging.info(
                '[PHOTO] - [{}] - Watermark has been successfully inserted to photo by link {} owned user {}.'.format(
                    datetime.datetime.now().strftime("%H:%M:%S-%d.%m.%Y"), link, message.from_user.id))
            os.remove(photo_abspath)  # Delete downloaded photo
            os.remove(photo_outpath)  # Delete edited photo


async def LinkVideoProcess(file_extension, message):
    if file_extension == 'mp4':
        print('mp4')
    elif file_extension == 'webm':
        print('webm')


@dp.message_handler(content_types=aiogram.types.ContentType.TEXT)
async def LinkProcess(message: aiogram.types.Message):
    try:
        user_input = message.text
        file_extension = user_input.split('.')[-1]
        if file_extension == 'mp4':
            print('mp4')
        elif file_extension == 'webm':
            print('wemb')
        elif file_extension == 'png' or file_extension == 'jpg':
            await LinkPhotoProcess(message, user_input)
        else:
            await message.answer("Try another link please.")
    except Exception:
        print(Exception)
        await message.answer('Link: {} - is invalid.'.format(user_input))

async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)
    # insert code here to run it after start


async def on_shutdown(dp):
    logging.warning('Shutting down..')

    # insert code here to run it before shutdown

    # Remove webhook (not acceptable in some cases)
    await bot.delete_webhook()

    # Close DB connection (if used)
    await dp.storage.close()
    await dp.storage.wait_closed()

    logging.warning('Bye!')
if __name__ == '__main__':
    #aiogram.executor.start_polling(dp, skip_updates=False)
    #exit(0)
    WEBHOOK_HOST = 'https://roomhacker.duckdns.org'
    WEBHOOK_PATH = '/watermark'
    WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

    # webserver settings
    WEBAPP_HOST = '0.0.0.0'  # or ip
    WEBAPP_PORT = 3001
    loop=asyncio.new_event_loop()
    aiogram.executor.start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        skip_updates=True,
        on_startup=on_startup,on_shutdown=on_shutdown,
        host=WEBAPP_HOST,
        port=WEBAPP_PORT,
    )
