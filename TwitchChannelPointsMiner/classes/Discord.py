import re
import time
from textwrap import dedent
from typing import Dict, Optional, Any
from functools import lru_cache

import requests

from TwitchChannelPointsMiner.classes.Settings import Events


class EventParser:
    """Parser für verschiedene Event-Message-Typen"""
    
    @staticmethod
    def parse_streamer_status(message: str) -> Optional[Dict[str, Any]]:
        """Parst Streamer Online/Offline Messages"""
        pattern = r"Streamer\(username=([^,]+),.*channel_points=([^)]+)\) is (Online|Offline)!"
        match = re.search(pattern, message)
        if match:
            return {
                'username': match.group(1),
                'channel_points': match.group(2),
                'status': match.group(3).lower()
            }
        return None

    @staticmethod
    def parse_points_gain(message: str) -> Optional[Dict[str, Any]]:
        """Parst Channel Points Gewinne (+X → Streamer...)"""
        pattern = r"[+](\d+) → Streamer\(username=([^,]+),.*channel_points=([^)]+)\) - Reason: (\w+)"
        match = re.search(pattern, message)
        if match:
            return {
                'gained': int(match.group(1)),
                'username': match.group(2),
                'channel_points': match.group(3),
                'reason': match.group(4)
            }
        return None

    @staticmethod
    def parse_bet_result(message: str) -> Optional[Dict[str, Any]]:
        """Parst Bet Ergebnisse (WIN/LOSE)"""
        if "Result: WIN" in message:
            gained_match = re.search(r'Gained: \+([^,)]+)', message)
            username_match = re.search(r'username=([^,]+)', message)
            points_match = re.search(r'channel_points=([^)]+)', message)
            
            if all([gained_match, username_match, points_match]):
                return {
                    'result': 'win',
                    'gained': gained_match.group(1),
                    'username': username_match.group(1),
                    'channel_points': points_match.group(1)
                }
        elif "Result: LOSE" in message:
            lost_match = re.search(r'Lost: \-([^,)]+)', message)
            username_match = re.search(r'username=([^,]+)', message)
            points_match = re.search(r'channel_points=([^)]+)', message)
            
            if all([lost_match, username_match, points_match]):
                return {
                    'result': 'lose',
                    'lost': lost_match.group(1),
                    'username': username_match.group(1),
                    'channel_points': points_match.group(1)
                }
        return None

    @staticmethod
    def parse_raid_join(message: str) -> Optional[Dict[str, Any]]:
        """Parst Raid Events"""
        pattern = r"Joining raid from Streamer\(username=([^,]+),.*\) to ([^!]+)!"
        match = re.search(pattern, message)
        if match:
            return {
                'from_username': match.group(1),
                'to_username': match.group(2)
            }
        return None

    @staticmethod
    def parse_bet_start(message: str) -> Optional[Dict[str, Any]]:
        """Parst Bet Start Events"""
        pattern = r"Place the bet after: ([^s]+)s for: EventPrediction.*username=([^,]+).*title=([^)]+)\)"
        match = re.search(pattern, message)
        if match:
            return {
                'wait_time': match.group(1),
                'username': match.group(2),
                'title': match.group(3)
            }
        return None

    @staticmethod
    def parse_bet_filter(message: str) -> Optional[Dict[str, Any]]:
        """Parst Bet Filter Messages (zu wenig Points)"""
        pattern = r"Streamer\(username=([^,]+),.*channel_points=([^)]+)\) have only (\d+) channel points and the minimum for bet is: (\d+)"
        match = re.search(pattern, message)
        if match:
            return {
                'username': match.group(1),
                'channel_points': match.group(2),
                'current_points': int(match.group(3)),
                'minimum_points': int(match.group(4))
            }
        return None

    @staticmethod
    def parse_chat_message(message: str) -> Optional[Dict[str, Any]]:
        """Parst Chat Messages"""
        pattern = r"([^\\s]+) at #([^\\s]+) wrote: (.+)"
        match = re.search(pattern, message)
        if match:
            return {
                'username': match.group(1),
                'channel': match.group(2),
                'content': match.group(3)
            }
        return None


class DiscordEmbedBuilder:
    """Builder für Discord Embed Messages"""
    
    # Farben für verschiedene Event-Typen - Schönere Discord-optimierte Palette
    COLORS = {
        'online': 0x2ecc71,      # Schönes Grün
        'offline': 0xe74c3c,     # Kräftiges Rot
        'points': 0x4a90e2,      # Elegantes Blau
        'win': 0x27ae60,         # Erfolgs-Grün
        'lose': 0xc0392b,        # Verlust-Rot
        'raid': 0xe74c3c,        # Kräftiges Rot für Action
        'bet': 0x3498db,         # Discord-Blau
        'filter': 0xf39c12,      # Warnung-Orange
        'chat': 0x95a5a6         # Dezentes Grau
    }

    @staticmethod
    def create_base_embed(username: str, title: str, color: str) -> Dict[str, Any]:
        """Erstellt Basis Embed Structure"""
        return {
            "username": "Twitch Channel Points Miner",
            "avatar_url": "https://i.imgur.com/X9fEkhT.png",
            "embeds": [{
                "title": title,
                "url": f"https://twitch.tv/{username}",
                "color": DiscordEmbedBuilder.COLORS.get(color, 0x708090),
                "thumbnail": {"url": get_streamer_icon_cached(username)},
                "fields": []
            }]
        }

    @staticmethod
    def add_field(embed: Dict[str, Any], name: str, value: str, inline: bool = False):
        """Fügt Field zu Embed hinzu"""
        embed["embeds"][0]["fields"].append({
            "name": name,
            "value": str(value),
            "inline": inline
        })

    @staticmethod
    def create_online_embed(data: Dict[str, Any]) -> Dict[str, Any]:
        """Erstellt Online Embed"""
        embed = DiscordEmbedBuilder.create_base_embed(
            data['username'], 
            f"🟢 {data['username']} ist jetzt LIVE!",
            'online'
        )
        
        embed["embeds"][0]["description"] = f"**Stream gestartet!** 🚀\n⭐ Zeit zum Punkte sammeln!"
        
        DiscordEmbedBuilder.add_field(embed, "💰 Aktuelle Points", data['channel_points'], True)
        DiscordEmbedBuilder.add_field(embed, "🎮 Status", "LIVE", True)
        DiscordEmbedBuilder.add_field(embed, "⏰ Seit", "Gerade eben", True)
        
        return embed

    @staticmethod
    def create_offline_embed(data: Dict[str, Any]) -> Dict[str, Any]:
        """Erstellt Offline Embed"""
        embed = DiscordEmbedBuilder.create_base_embed(
            data['username'], 
            f"🔴 {data['username']} ist jetzt OFFLINE",
            'offline'
        )
        
        embed["embeds"][0]["description"] = f"**Stream beendet** 😴\n📊 Session abgeschlossen!"
        
        DiscordEmbedBuilder.add_field(embed, "💰 Finale Points", data['channel_points'], True)
        DiscordEmbedBuilder.add_field(embed, "🎮 Status", "OFFLINE", True)
        DiscordEmbedBuilder.add_field(embed, "✅ Session", "Beendet", True)
        
        return embed

    @staticmethod
    def create_points_embed(data: Dict[str, Any]) -> Dict[str, Any]:
        """Erstellt Points Gain Embed"""
        reason = data['reason']
        
        if reason == 'WATCH':
            return DiscordEmbedBuilder.create_watch_embed(data)
        elif reason == 'CLAIM':
            return DiscordEmbedBuilder.create_claim_embed(data)
        elif reason == 'RAID':
            return DiscordEmbedBuilder.create_raid_points_embed(data)
        else:
            # Fallback für andere Reasons
            embed = DiscordEmbedBuilder.create_base_embed(
                data['username'],
                f"🚀 +{data['gained']} - {data['username']}",
                'points'
            )
            DiscordEmbedBuilder.add_field(embed, "Grund", data['reason'])
            DiscordEmbedBuilder.add_field(embed, "Neue Channel Points", data['channel_points'])
            return embed

    @staticmethod
    def create_watch_embed(data: Dict[str, Any]) -> Dict[str, Any]:
        """Erstellt spezielles Watch Embed - kompakt und elegant"""
        embed = DiscordEmbedBuilder.create_base_embed(
            data['username'],
            f"👁️ Watching {data['username']}",
            'points'
        )
        
        # Kompakte Darstellung
        embed["embeds"][0]["description"] = f"**+{data['gained']} Points** 📺\n💰 Total: **{data['channel_points']}**"
        embed["embeds"][0]["color"] = 0x4a90e2  # Schönes Blau
        
        # Kleineres Thumbnail für weniger Platz
        embed["embeds"][0]["thumbnail"] = {"url": get_streamer_icon_cached(data['username'])}
        
        return embed

    @staticmethod
    def create_claim_embed(data: Dict[str, Any]) -> Dict[str, Any]:
        """Erstellt spezielles Claim Embed - hervorgehoben da seltener"""
        embed = DiscordEmbedBuilder.create_base_embed(
            data['username'],
            f"🎁 Bonus Claimed bei {data['username']}!",
            'points'
        )
        
        embed["embeds"][0]["description"] = f"**Bonus erhalten!** 🎉"
        embed["embeds"][0]["color"] = 0xf39c12  # Gold/Orange
        
        # Hervorgehobene Fields
        DiscordEmbedBuilder.add_field(embed, "💎 Bonus Points", f"+{data['gained']}", True)
        DiscordEmbedBuilder.add_field(embed, "💰 Gesamt Points", data['channel_points'], True)
        DiscordEmbedBuilder.add_field(embed, "⭐ Typ", "Channel Bonus", True)
        
        return embed

    @staticmethod
    def create_raid_points_embed(data: Dict[str, Any]) -> Dict[str, Any]:
        """Erstellt spezielles Raid Points Embed"""
        embed = DiscordEmbedBuilder.create_base_embed(
            data['username'],
            f"🎭 Raid Bonus bei {data['username']}!",
            'raid'
        )
        
        embed["embeds"][0]["description"] = f"**Raid-Teilnahme belohnt!** ⚔️"
        embed["embeds"][0]["color"] = 0x9b59b6  # Lila
        
        # Raid-spezifische Fields
        DiscordEmbedBuilder.add_field(embed, "⚔️ Raid Bonus", f"+{data['gained']}", True)
        DiscordEmbedBuilder.add_field(embed, "💰 Neue Points", data['channel_points'], True)
        DiscordEmbedBuilder.add_field(embed, "🏆 Event", "Raid Participation", True)
        
        return embed

    @staticmethod
    def create_bet_embed(data: Dict[str, Any]) -> Dict[str, Any]:
        """Erstellt Bet Result Embed"""
        if data['result'] == 'win':
            embed = DiscordEmbedBuilder.create_base_embed(
                data['username'],
                f"🎉 {data['username']} - Prediction Gewonnen!",
                'win'
            )
            DiscordEmbedBuilder.add_field(embed, "Gewinn", f"+{data['gained']}")
        else:
            embed = DiscordEmbedBuilder.create_base_embed(
                data['username'],
                f"😢 {data['username']} - Prediction Verloren!",
                'lose'
            )
            DiscordEmbedBuilder.add_field(embed, "Verlust", f"-{data['lost']}")
        
        DiscordEmbedBuilder.add_field(embed, "Neue Channel Points", data['channel_points'])
        return embed

    @staticmethod
    def create_raid_embed(data: Dict[str, Any]) -> Dict[str, Any]:
        """Erstellt Raid Embed für Raid-Teilnahme"""
        embed = DiscordEmbedBuilder.create_base_embed(
            data['from_username'],
            f"⚔️ Raid Event - Zeit für Action!",
            'raid'
        )
        
        embed["embeds"][0]["description"] = f"**Wir raiden zusammen!** 🚀\n🎯 Ziel: **{data['to_username']}**"
        embed["embeds"][0]["color"] = 0xe74c3c  # Kräftiges Rot
        
        # Raid-spezifische Fields mit besserer Formatierung
        DiscordEmbedBuilder.add_field(embed, "📡 Von Channel", data['from_username'], True)
        DiscordEmbedBuilder.add_field(embed, "🎯 Ziel Channel", data['to_username'], True)
        DiscordEmbedBuilder.add_field(embed, "🎭 Event", "Community Raid", True)
        
        # Twitch-URL für das Ziel setzen
        embed["embeds"][0]["url"] = f"https://twitch.tv/{data['to_username']}"
        
        return embed

    @staticmethod
    def create_bet_start_embed(data: Dict[str, Any]) -> Dict[str, Any]:
        """Erstellt Bet Start Embed"""
        embed = DiscordEmbedBuilder.create_base_embed(
            data['username'],
            f"⏰ Neue Prediction bei {data['username']}!",
            'bet'
        )
        DiscordEmbedBuilder.add_field(embed, "Titel", data['title'])
        DiscordEmbedBuilder.add_field(embed, "Wartezeit", f"{data['wait_time']}s")
        return embed

    @staticmethod
    def create_filter_embed(data: Dict[str, Any]) -> Dict[str, Any]:
        """Erstellt Bet Filter Embed"""
        embed = DiscordEmbedBuilder.create_base_embed(
            data['username'],
            f"⚠️ {data['username']} - Prediction übersprungen",
            'filter'
        )
        
        missing_points = data['minimum_points'] - data['current_points']
        embed["embeds"][0]["description"] = f"**Nicht genug Points für Bet** 💸\n🎯 Noch **{missing_points:,}** Points sammeln!"
        
        DiscordEmbedBuilder.add_field(embed, "💰 Aktuelle Points", f"{data['current_points']:,}", True)
        DiscordEmbedBuilder.add_field(embed, "🎯 Minimum benötigt", f"{data['minimum_points']:,}", True)
        DiscordEmbedBuilder.add_field(embed, "📈 Noch sammeln", f"{missing_points:,}", True)
        
        return embed


# Icon Caching mit TTL
_icon_cache = {}
_cache_ttl = 3600  # 1 Stunde


@lru_cache(maxsize=100)
def get_streamer_icon_cached(username: str) -> Optional[str]:
    """Cached Version der Icon-Funktion für bessere Performance"""
    current_time = time.time()
    
    # Cache Check
    if username in _icon_cache:
        cached_data = _icon_cache[username]
        if current_time - cached_data['timestamp'] < _cache_ttl:
            return cached_data['url']
    
    # Icon neu laden
    try:
        response = requests.get(f"https://www.twitch.tv/{username}", timeout=5)
        match = re.search(r'meta property="og:image" content="(.*?)"', response.text)
        icon_url = match.group(1) if match else None
        
        # In Cache speichern
        _icon_cache[username] = {
            'url': icon_url,
            'timestamp': current_time
        }
        
        return icon_url
    except:
        return None


class Discord:
    """Verbesserte Discord Klasse mit Event-Parser und Embed-System"""
    __slots__ = ["webhook_api", "events", "_session"]

    def __init__(self, webhook_api: str, events: list):
        self.webhook_api = webhook_api
        self.events = [str(e) for e in events]
        self._session = requests.Session()  # Session für bessere Performance

    def send(self, message: str, event: Events) -> None:
        """Haupt Send-Methode mit Event-basiertem Routing"""
        if str(event) not in self.events:
            return

        # Event-spezifische Behandlung
        embed_data = None
        
        try:
            if event == Events.STREAMER_ONLINE:
                data = EventParser.parse_streamer_status(message)
                if data and data['status'] == 'online':
                    embed_data = DiscordEmbedBuilder.create_online_embed(data)
            
            elif event == Events.STREAMER_OFFLINE:
                data = EventParser.parse_streamer_status(message)
                if data and data['status'] == 'offline':
                    embed_data = DiscordEmbedBuilder.create_offline_embed(data)
            
            elif event in [Events.GAIN_FOR_WATCH, Events.GAIN_FOR_CLAIM, Events.GAIN_FOR_RAID]:
                data = EventParser.parse_points_gain(message)
                if data:
                    embed_data = DiscordEmbedBuilder.create_points_embed(data)
            
            elif event in [Events.BET_WIN, Events.BET_LOSE]:
                data = EventParser.parse_bet_result(message)
                if data:
                    embed_data = DiscordEmbedBuilder.create_bet_embed(data)
            
            elif event == Events.JOIN_RAID:
                data = EventParser.parse_raid_join(message)
                if data:
                    embed_data = DiscordEmbedBuilder.create_raid_embed(data)
            
            elif event == Events.BET_START:
                data = EventParser.parse_bet_start(message)
                if data:
                    embed_data = DiscordEmbedBuilder.create_bet_start_embed(data)
            
            elif event == Events.BET_FILTERS:
                data = EventParser.parse_bet_filter(message)
                if data:
                    embed_data = DiscordEmbedBuilder.create_filter_embed(data)
            
            elif event == Events.CHAT_MENTION:
                data = EventParser.parse_chat_message(message)
                if data:
                    # Einfache Text-Message für Chat
                    self._send_simple_message(f"💬 **{data['username']}** in #{data['channel']}: {data['content']}")
                    return

            # Embed senden falls erstellt
            if embed_data:
                self._send_embed(embed_data)
            else:
                # Fallback: Simple Message
                self._send_simple_message(message)
                
        except Exception as e:
            print(f"Discord Error: {e}")
            # Fallback bei Fehlern
            self._send_simple_message(message)

    def _send_embed(self, embed_data: Dict[str, Any]) -> None:
        """Sendet Embed Message"""
        try:
            self._session.post(
                url=self.webhook_api,
                json=embed_data,
                timeout=10
            )
        except requests.RequestException as e:
            print(f"Discord Embed Send Error: {e}")

    def _send_simple_message(self, message: str) -> None:
        """Sendet einfache Text Message"""
        try:
            self._session.post(
                url=self.webhook_api,
                data={
                    "content": dedent(str(message)),
                    "username": "Twitch Channel Points Miner",
                    "avatar_url": "https://i.imgur.com/X9fEkhT.png",
                },
                timeout=10
            )
        except requests.RequestException as e:
            print(f"Discord Simple Send Error: {e}")

    def __del__(self):
        """Cleanup Session"""
        if hasattr(self, '_session'):
            self._session.close()


# Backwards compatibility
def get_streamer_icon(username):
    """Legacy function für Backwards Compatibility"""
    return get_streamer_icon_cached(username)
