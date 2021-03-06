import json
import mimetypes
import os
import shlex
import subprocess
import uuid
import time
import pprint

from kinto_client import Client as Kinto, exceptions as kinto_exceptions
import requests
import telepot


TOKEN = os.getenv("TOKEN")
WALL_URL = os.getenv("WALL_URL", "http://leplatrem.github.io/kinto-telegram-wall/")
MOZILLA_DEMO_SERVER = "https://kinto.dev.mozaws.net/v1"
SERVER_URL = os.getenv("SERVER_URL", MOZILLA_DEMO_SERVER)
SERVER_AUTH = os.getenv("SERVER_AUTH", "botuser:secret")
BUCKET = os.getenv("BUCKET", "kintobot")
COLLECTION = os.getenv("COLLECTION", "wall")
DOWNLOAD_PATH = os.getenv("DOWNLOAD_PATH", ".")
DOWNLOAD_MAX_SIZE = int(os.getenv("DOWNLOAD_MAX_SIZE", 5 * 1000 * 1000))
CONTACT_SUPPORT = os.getenv("CONTACT_SUPPORT", "@leplatrem")

DOWNLOAD_TYPES = ("voice", "sticker", "photo", "audio", "document", "video")
BUCKET_PERMISSIONS = {"collection:create": ["system.Authenticated"]}
COLLECTION_PERMISSIONS = {"record:create": ["system.Authenticated"]}
RECORD_PERMISSIONS = {"read": ["system.Everyone"]}
COMMAND_MP4_TO_WEBM = os.getenv("COMMAND_MP4_TO_WEBM", 'ffmpeg -i "{src}" "{dest}"')
COMMAND_WEBP_TO_PNG = os.getenv("COMMAND_WEBP_TO_PNG", COMMAND_MP4_TO_WEBM)  # Recent ffmpeg rocks.
THUMB_UP = u'\U0001f44d'


mimetypes.add_type("audio/ogg", ".oga")
mimetypes.add_type("image/ogg", ".ogg")
mimetypes.add_type("image/webp", ".webp")


def kinto_init():
    try:
        kinto.create_bucket(BUCKET, permissions=BUCKET_PERMISSIONS)
    except kinto_exceptions.KintoException as e:
        if e.response.status_code not in (403, 412):
            raise e
        print("Bucket '%s' already exists." % BUCKET)
    try:
        kinto.create_collection(COLLECTION, bucket=BUCKET, permissions=COLLECTION_PERMISSIONS)
    except kinto_exceptions.KintoException as e:
        if e.response.status_code not in (403, 412):
            raise e
        print("Collection '%s' already exists." % COLLECTION)


def kinto_create_record(record):
    # Since demo server is flushed every morning, recreate bucket/collection!
    if SERVER_URL == MOZILLA_DEMO_SERVER:
        kinto_init()

    kinto.create_record(data=record, permissions=RECORD_PERMISSIONS,
                        collection=COLLECTION, bucket=BUCKET)


def kinto_create_attachment(record, tmpfile, filename, mimetype):
    # Since demo server is flushed every morning, recreate bucket/collection!
    if SERVER_URL == MOZILLA_DEMO_SERVER:
        kinto_init()

    record_id = str(uuid.uuid4())
    endpoint = kinto.endpoints.get("record", id=record_id, bucket=BUCKET, collection=COLLECTION)
    endpoint += "/attachment"

    files = [("attachment", (filename, open(tmpfile, "rb"), mimetype))]
    payload = {"data": json.dumps(record), "permissions": json.dumps(RECORD_PERMISSIONS)}
    response = requests.post(SERVER_URL + endpoint, data=payload, files=files, auth=kinto.session.auth)
    response.raise_for_status()
    pprint.pprint(response.json())


def download_from_telegram(attachment):
    file_id = attachment["file_id"]
    filename = attachment.get("file_name")
    if not filename:
        filepath = attachment.get("file_path")
        if not filename:
            fileinfo = bot.getFile(file_id)
            filepath = fileinfo["file_path"]
        filename = os.path.basename(filepath)

    mimetype = attachment.get("mime_type")
    if not mimetype:
        mimetype, _ = mimetypes.guess_type(filename)

    if mimetype:
        extension = mimetypes.guess_extension(mimetype)
    elif "." in filename:
        extension = "." + filename.rsplit(".", 1)[-1]

    destination = os.path.join(DOWNLOAD_PATH, file_id) + (extension or '')
    bot.downloadFile(file_id, destination)
    print("Downloaded %s" % destination)

    # Transcode WebP if possible.
    if extension == '.webp':
        try:
            newdestination = destination.replace('.webp', '.png')
            command = COMMAND_WEBP_TO_PNG.format(src=destination, dest=newdestination)
            subprocess.check_call(shlex.split(command))
            os.remove(destination)
            print("'%s' successfull" % command)
            destination = newdestination
            filename = os.path.basename(destination)
            mimetype = 'image/png'
        except Exception as e:
            print("'%s' failed: %s" % (command, e))

    # Transcode 3gpp if possible.
    if extension == '.mp4':
        try:
            newdestination = destination.replace('.mp4', '.webm')
            command = COMMAND_MP4_TO_WEBM.format(src=destination, dest=newdestination)
            subprocess.check_call(shlex.split(command))
            print("'%s' successfull" % command)
            os.remove(destination)
            destination = newdestination
            filename = os.path.basename(destination)
            mimetype = 'video/webm'
        except Exception as e:
            print("'%s' failed: %s" % (command, e))

    return (destination, filename, mimetype)


def handle(msg):
    pprint.pprint(msg)

    msg_type, chat_type, chat_id = telepot.glance2(msg)

    if msg.get("text", "").startswith("/"):
        welcome = (
            "Hello!\n"
            "Any message, picture, sound, video sent to me will be displayed "
            "live on {wall_url}\n"
            "This project is open source!\n"
            "Check out https://github.com/leplatrem/kinto-telegram-wall#readme"
        ).format(wall_url=WALL_URL)
        bot.sendMessage(chat_id, welcome)
        return

    # Attributes sent to Kinto.
    record = {"date": msg["date"],
              "from": {"first_name": msg["from"]["first_name"]}}
    content = msg[msg_type]

    tmpfile = None
    try:
        if msg_type not in DOWNLOAD_TYPES:
            record[msg_type] = content
            kinto_create_record(record)
        else:
            if msg_type == "photo":
                content = content[-1]

            filesize = content.get("file_size")
            if filesize > DOWNLOAD_MAX_SIZE:
                bot.sendMessage(chat_id, "File is too big!")
                return

            tmpfile, filename, mimetype = download_from_telegram(content)
            print((tmpfile, filename, mimetype))
            kinto_create_attachment(record, tmpfile, filename, mimetype)
        bot.sendMessage(chat_id, THUMB_UP)
    except Exception as e:
        print(e)
        bot.sendMessage(chat_id, "An error occured. Contact %s" % CONTACT_SUPPORT)
    finally:
        if tmpfile and os.path.exists(tmpfile):
            os.remove(tmpfile)


if __name__ == "__main__":
    auth = tuple(SERVER_AUTH.split(":"))
    print("Connect to %s with user '%s'." % (SERVER_URL, auth[0]))
    kinto = Kinto(server_url=SERVER_URL, auth=auth)
    kinto_init()

    bot = telepot.Bot(TOKEN)
    bot.notifyOnMessage(handle)
    print("Listening ...")

    # Keep the program running.
    while 1:
        time.sleep(10)
