import json
import mimetypes
import os
import uuid
import time
import pprint

from kinto_client import Client as Kinto, exceptions as kinto_exceptions
import requests
import telepot


DEMO_SERVER_URL = "https://kinto.dev.mozaws.net/v1"
TOKEN = os.getenv("TOKEN")
SERVER_URL = os.getenv("SERVER_URL", DEMO_SERVER_URL)
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
    if SERVER_URL == DEMO_SERVER_URL:
        kinto_init()

    kinto.create_record(data=record, permissions=RECORD_PERMISSIONS,
                        collection=COLLECTION, bucket=BUCKET)


def kinto_create_attachment(record, tmpfile, filename, mimetype):
    # Since demo server is flushed every morning, recreate bucket/collection!
    if SERVER_URL == DEMO_SERVER_URL:
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

    return (destination, filename, mimetype)


def handle(msg):
    pprint.pprint(msg)

    msg_type, chat_type, chat_id = telepot.glance2(msg)

    if msg.get("text", "").startswith("/"):
        welcome = (
            "Hello!\n"
            "This project is open source!\n"
            "Check out https://github.com/leplatrem/kinto-telegram-wall#readme"
        )
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
