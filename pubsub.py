import json
import threading
import time
from random import randrange
import websocket  # pip install websocket-client
from claim_bonus import claim_channel_points_bonus
from raid import update_raid, Raid
from twitch_data import *

from classes.WebsocketsPool import WebsocketsPool
from classes.PubsubTopic import PubsubTopic

# For documentation on Twitch PubSub API, see https://dev.twitch.tv/docs/pubsub


def listen_for_channel_points():
    ws_pool = WebsocketsPool()
    for topic in get_needed_topics():
        ws_pool.submit(topic)


def get_needed_topics():
    topics = [PubsubTopic("community-points-user-v1")]
    for streamer_login in get_streamer_logins():
        topics.append(PubsubTopic("video-playback-by-id", streamer_login))
        topics.append(PubsubTopic("raid", streamer_login))
    return topics


def on_open(ws):
    def run():
        ping(ws)

        all_topics = get_needed_topics()
        for topic in all_topics:
            listen_for_topic(ws, topic)

        while not ws.is_closed:
            ping(ws)
            time.sleep(30)

    threading.Thread(target=run).start()


last_message_time = 0
last_message_type = None


def on_message(ws, message):
    global last_message_time, last_message_type
    response = json.loads(message)

    if response["type"] == "MESSAGE":
        # print("Received message: ", response)
        data = response["data"]
        topic, topic_user = data["topic"].split(".")
        message = json.loads(data["message"])
        message_type = message["type"]
        message_data = None
        if "data" in message:
            message_data = message["data"]

        # If we have more than one PubSub connection, messages may be duplicated
        if time.time() - last_message_time < 0.1 and last_message_type == message_type:
            last_message_time = time.time()
            return
        last_message_time = time.time()
        last_message_type = message_type

        if topic == "community-points-user-v1":
            if message_type == "points-earned":
                channel_id = message_data["channel_id"]
                if channel_id in get_streamer_ids():
                    new_balance = message_data["balance"]["balance"]
                    channel_login = get_login_by_channel_id(channel_id)
                    reason_name = get_reason_name(message_data["point_gain"]["reason_code"])
                    print(f"{new_balance} channel points for {channel_login}! Reason: {reason_name}.")
            elif message_type == "claim-available":
                channel_id = message_data["claim"]["channel_id"]
                if channel_id in get_streamer_ids():
                    claim_id = message_data["claim"]["id"]
                    streamer_login = get_login_by_channel_id(channel_id)
                    claim_channel_points_bonus(streamer_login, claim_id)

        elif topic == "video-playback-by-id":
            channel_login = get_login_by_channel_id(topic_user)
            if message_type == "stream-down":
                set_offline(channel_login)
            elif message_type == "viewcount":
                check_online(channel_login)
            # there is stream-up message type, but it's sent earlier than the API updates

        elif topic == "raid":
            channel_login = get_login_by_channel_id(topic_user)
            if message_type == "raid_update_v2":
                # streamer_login is going to raid someone
                raid_info = message["raid"]
                raid = Raid(raid_info["id"], raid_info["target_login"])
                update_raid(channel_login, raid)

    elif response["type"] == "RESPONSE" and len(response.get("error", "")) > 0:
        raise RuntimeError(f"Error while trying to listen for a topic: {response}")

    elif response["type"] == "RECONNECT":
        WebsocketsPool.handle_websocket_reconnection(ws)


def get_reason_name(code):
    return code.replace("_", " ").replace("CLAIM", "bonus claimed").lower()


def listen_for_topic(ws, topic):
    data = {"topics": [str(topic)]}
    if topic.is_user_topic:
        data["auth_token"] = get_auth_token()

    nonce = create_nonce()
    send(ws, {"type": "LISTEN", "nonce": nonce, "data": data})


def ping(ws):
    send(ws, {"type": "PING"})


def send(ws, request):
    request_str = json.dumps(request, separators=(',', ':'))
    ws.send(request_str)

# https://en.wikipedia.org/wiki/Cryptographic_nonce
def create_nonce(length=30):
    nonce = ""
    for i in range(length):
        char_index = randrange(0, 10 + 26 + 26)
        if char_index < 10:
            char = chr(ord('0') + char_index)
        elif char_index < 10 + 26:
            char = chr(ord('a') + char_index - 10)
        else:
            char = chr(ord('A') + char_index - 26 - 10)
        nonce += char

    return nonce