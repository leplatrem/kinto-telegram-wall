import json
import mimetypes
import os
import uuid
import time
import pprint

from kinto_client import Client as Kinto
import requests
import telepot


TOKEN = os.getenv("TOKEN")
SERVER_URL = os.getenv("SERVER_URL", "https://kinto.dev.mozaws.net/v1")
KINTO_AUTH = os.getenv("SERVER_AUTH", "botuser:secret")
BUCKET = os.getenv("BUCKET", "kintobot")
COLLECTION = os.getenv("COLLECTION", "wall")
DOWNLOAD_PATH = os.getenv("DOWNLOAD_PATH", ".")

DOWNLOAD_TYPES = ("voice", "sticker", "photo", "audio", "document", "video")
RECORD_PERMISSIONS = {"read": ["system.Everyone"]}

mimetypes.add_type("audio/ogg", ".oga")
mimetypes.add_type("image/ogg", ".ogg")
mimetypes.add_type("image/webp", ".webp")



kinto = Kinto(server_url=SERVER_URL, auth=tuple(KINTO_AUTH.split(":")))


def kinto_init():
    kinto.create_bucket(BUCKET, safe=False)
    kinto.create_collection(COLLECTION, bucket=BUCKET, safe=False)


def kinto_create_record(msg):
    kinto.create_record(data=msg, permissions=RECORD_PERMISSIONS,
                        collection=COLLECTION, bucket=BUCKET)


def kinto_create_attachment(msg, tmpfile, filename, mimetype):
    record_id = str(uuid.uuid4())
    endpoint = kinto.endpoints.get("record", id=record_id, bucket=BUCKET, collection=COLLECTION)
    endpoint += "/attachment"

    files = [("attachment", (filename, open(tmpfile, "rb"), mimetype))]
    payload = {"data": json.dumps(msg), "permissions": json.dumps(RECORD_PERMISSIONS)}
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

    if msg_type not in DOWNLOAD_TYPES:
        kinto_create_record(msg)
    else:
        attachment = msg.pop(msg_type)
        if msg_type == "photo":
            attachment = attachment[-1]

        tmpfile, filename, mimetype = download_from_telegram(attachment)
        kinto_create_attachment(msg, tmpfile, filename, mimetype)
        os.remove(tmpfile)


if __name__ == "__main__":
    kinto_init()

    bot = telepot.Bot(TOKEN)
    bot.notifyOnMessage(handle)
    print("Listening ...")

    # Keep the program running.
    while 1:
        time.sleep(10)
