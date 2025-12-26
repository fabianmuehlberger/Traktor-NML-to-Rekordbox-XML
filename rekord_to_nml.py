import base64
import hashlib
import random
import uuid
import xml.etree.ElementTree as ET
import sys
from os.path import exists

from consts import KEY_TO_CODE
from utils import (
    get_attribute,
    format_date,
    get_tonalikey,
    get_track_color,
    get_cue_type,
    set_conversion,
    get_location,
    set_cue_color,
    today,
)


class Rekordbox2Traktor:
    def __init__(self):
        self.root = None
        self.track = None
        self.cues = []
        self.track_index = 0
        self.cue_index = 0
        self.track_info = {}
        self.tracks = []
        self.track_id_map = {}  # Maps Rekordbox TrackID to NML file path

    def generate_audio_id(self):
        # AUDIO_ID contains Base64-encoded audio fingerprint data (spectral analysis, transients, beat info) that Traktor uses for validation.
        # Since we can't generate authentic fingerprints without Native Instruments' algorithms, we use a static placeholder.
        # Imported tracks might require re-analysis in Traktor.
        return "AWAWZmRENDMzMzf//////////////////////f/////////////////////s/////////////////////5b///7//////////+//////af/////////////////////+///////////f/////////1n/////////9Y///////////f/////////+r/7///////9XYzMzM0MyMzJUMzNDNDMzRDn//////////////////////f/////////////////////e/////////////////////3r+/+////////7u7u/v////vf//7////////v/+//////+FZneYYQAAAA=="

    def set_track_info(self, track):
        # Helper function to safely convert to float with default
        def safe_float(value, default=0.0):
            try:
                return float(value) if value else default
            except (ValueError, TypeError):
                return default
        
        # Helper function to safely get attribute with default
        def safe_get_attr(attr_name, default=""):
            val = get_attribute(track, attr_name)
            return val if val else default
        
        avg_bpm = safe_get_attr("AverageBpm", "120.0")
        bitrate = safe_get_attr("BitRate", "320")
        
        self.track_info = {
            'id': get_attribute(track, "TrackId") or uuid.uuid4().hex[:8],
            'title': safe_get_attr("Name"),
            'artist': safe_get_attr("Artist"),
            'album': safe_get_attr("Album"),
            'key': get_tonalikey(safe_get_attr("Tonality")),
            'bpm': safe_float(avg_bpm, 120.0),
            'color': get_track_color(safe_get_attr("Colour")),
            'genre': safe_get_attr("Genre"),
            'playtime': safe_get_attr("TotalTime", "0"),
            'playcount': safe_get_attr("PlayCount", "0"),
            'bitrate': safe_float(bitrate, 320.0) * 1000,
            'import_date': format_date(safe_get_attr("DateAdded")),
            'modif_date': format_date(safe_get_attr("DateModified")),
            'last_played': format_date(safe_get_attr("LastPlayed")),
            'ranking': safe_get_attr("Rating", "0"),
            'filesize': safe_get_attr("Size", "0"),
            'location': safe_get_attr("Location"),
            'comments': safe_get_attr("Comments")
        }

        return self.track_info

    @staticmethod
    def sec_2_ms(time_sec):
        return float(time_sec) * 1000 if time_sec else 0

    def add_location(self):
        location_data = get_location(self.track_info['location'])
        location = ET.SubElement(self.track, "LOCATION",
                                 DIR=location_data["DIR"],
                                 FILE=location_data["FILE"],
                                 VOLUME=location_data["VOLUME"],
                                 VOLUMEID=location_data["VOLUME"])
        return location

    def add_album(self):
        if self.track_info['album']:
            album = ET.SubElement(self.track, "ALBUM", TITLE=self.track_info['album'])
            return album
        return None

    def add_modification_info(self):
        modif = ET.SubElement(self.track, "MODIFICATION_INFO", AUTHOR_TYPE="user")
        return modif

    def add_info(self):
        # Handle empty playtime with default value
        playtime = self.track_info['playtime'] or "0"
        try:
            playtime_float = float(playtime)
        except (ValueError, TypeError):
            playtime_float = 0.0
        
        # Handle missing key with safe lookup
        key_code = KEY_TO_CODE.get(self.track_info['key'], "10d")  # Default to C major
        
        info_attrs = {
            "BITRATE": str(int(self.track_info['bitrate'])),
            "GENRE": self.track_info['genre'] or "",
            "KEY": key_code,
            "PLAYCOUNT": self.track_info['playcount'] or "0",
            "PLAYTIME": playtime,
            "PLAYTIME_FLOAT": f"{playtime_float:.6f}",
            "RANKING": self.track_info['ranking'] or "0",
            "IMPORT_DATE": self.track_info['import_date'] or "",
            "LAST_PLAYED": self.track_info['last_played'] or "",
            "FLAGS": "12",
            # "FILESIZE": str(int(float(self.track_info['filesize']) / 1024)) if self.track_info['filesize'] else "0",
            "COLOR": self.track_info['color'] or ""
        }

        if self.track_info['comments']:
            info_attrs["COMMENT"] = self.track_info['comments']

        info = ET.SubElement(self.track, "INFO", **info_attrs)
        return info

    def add_tempo(self):
        tempo = ET.SubElement(self.track, "TEMPO",
                              BPM=f"{self.track_info['bpm']:.6f}",
                              BPM_QUALITY="100.000000")
        return tempo

    def add_loudness(self):
        loudness = ET.SubElement(self.track, "LOUDNESS",
                                 PEAK_DB="-1.0",
                                 PERCEIVED_DB="-1.0",
                                 ANALYZED_DB="-1.0")
        return loudness

    def add_musical_key(self):
        musical_key = ET.SubElement(self.track, "MUSICAL_KEY", VALUE=self.track_info['key'])
        return musical_key

    def add_beatmarker(self, start_ms, bpm, is_autogrid=False):
        name = "AutoGrid" if is_autogrid else "Beat Marker"

        cue = ET.SubElement(self.track, "CUE_V2",
                            NAME=name,
                            DISPL_ORDER="0",
                            TYPE="4",
                            START=f"{start_ms:.6f}",
                            LEN="0.000000",
                            REPEATS="-1",
                            HOTCUE="-1")

        grid = ET.SubElement(cue, "GRID", BPM=f"{bpm:.6f}")

        return cue

    def add_autogrid(self, start_ms):
        cue = ET.SubElement(self.track, "CUE_V2",
                            NAME="AutoGrid",
                            DISPL_ORDER="0",
                            TYPE="0",
                            START=f"{start_ms:.6f}",
                            LEN="0.000000",
                            REPEATS="-1",
                            HOTCUE="0",
                            COLOR="#FFFFFF")

        return cue

    def add_cue(self, position_mark):
        cue_type = get_attribute(position_mark, "Type")
        start_sec = get_attribute(position_mark, "Start")
        end_sec = get_attribute(position_mark, "End")
        num = get_attribute(position_mark, "Num")
        name = get_attribute(position_mark, "Name") or "n.n."

        start_ms = self.sec_2_ms(start_sec)
        loop_length = 0
        if end_sec:
            loop_length = self.sec_2_ms(end_sec) - start_ms

        hotcue = num if num and num != "-1" else str(self.cue_index)

        cue_attrs = {
            "NAME": name,
            "DISPL_ORDER": "0",
            "TYPE": get_cue_type(cue_type),
            "START": f"{start_ms:.6f}",
            "LEN": f"{loop_length:.6f}",
            "REPEATS": "-1",
            "HOTCUE": hotcue
        }

        cue = ET.SubElement(self.track, "CUE_V2", **cue_attrs)
        r = get_attribute(position_mark, "Red")
        g = get_attribute(position_mark, "Green")
        b = get_attribute(position_mark, "Blue")

        if r and g and b:
            set_cue_color(cue, r=r, g=g, b=b)

        self.cue_index += 1
        return cue

    def process_tempo(self, track):
        tempo_elements = track.findall("TEMPO")

        if not tempo_elements:
            self.add_beatmarker(0, self.track_info['bpm'], is_autogrid=True)
            self.add_autogrid(0)

        elif len(tempo_elements) == 1:
            tempo = tempo_elements[0]
            start_sec = float(get_attribute(tempo, "Inizio") or "0")
            bpm = float(get_attribute(tempo, "Bpm") or str(self.track_info['bpm']))
            start_ms = self.sec_2_ms(start_sec)

            self.add_beatmarker(start_ms, bpm, is_autogrid=True)
            self.add_autogrid(start_ms)

        else:
            for i, tempo in enumerate(tempo_elements):
                start_sec = float(get_attribute(tempo, "Inizio") or "0")
                bpm = float(get_attribute(tempo, "Bpm") or str(self.track_info['bpm']))
                start_ms = self.sec_2_ms(start_sec)

                is_autogrid = (i == 0)
                self.add_beatmarker(start_ms, bpm, is_autogrid=is_autogrid)

                if is_autogrid:
                    self.add_autogrid(start_ms)

    def process_cues(self, track):
        position_marks = track.findall("POSITION_MARK")

        for position_mark in position_marks:
            name = get_attribute(position_mark, "Name")
            if name == "AutoGrid":
                continue

            self.add_cue(position_mark)

    def reset_track(self):
        self.track = None
        self.cues = []
        self.cue_index = 1
        self.track_info = {}

    def add_entry(self, collection):
        info = self.track_info

        entry = ET.SubElement(
            collection,
            "ENTRY",
            MODIFIED_DATE= info['modif_date'] or today(),
            MODIFIED_TIME="0", # TODO change
            AUDIO_ID=self.generate_audio_id(),
            TITLE=info['title'],
            ARTIST=info['artist']
        )
        return entry

    def add_playlists_section(self):
        """Create the PLAYLISTS section structure."""
        playlists = ET.SubElement(self.root, "PLAYLISTS")
        root_node = ET.SubElement(playlists, "NODE", TYPE="FOLDER", NAME="$ROOT")
        return root_node

    def process_playlist_node(self, rekordbox_node, parent_subnodes):
        """
        Recursively process a Rekordbox playlist node (folder or playlist).
        
        Args:
            rekordbox_node: Rekordbox NODE element
            parent_subnodes: Parent NML SUBNODES element (or NODE element if it needs SUBNODES created)
        """
        node_type = get_attribute(rekordbox_node, "Type")
        node_name = get_attribute(rekordbox_node, "Name")
        
        if not node_name:
            return
        
        if node_type == "0":  # Folder
            # Create a folder node in NML
            folder_node = ET.SubElement(parent_subnodes, "NODE", TYPE="FOLDER", NAME=node_name)
            subnodes = ET.SubElement(folder_node, "SUBNODES")
            
            # Process child nodes
            child_count = 0
            for child in rekordbox_node.findall("NODE"):
                self.process_playlist_node(child, subnodes)
                child_count += 1
            
            subnodes.set("COUNT", str(child_count))
            
        elif node_type == "1":  # Playlist
            # Get all TRACK elements from the Rekordbox playlist
            track_elements = rekordbox_node.findall("TRACK")
            
            if not track_elements:
                return
            
            # Create playlist node in NML
            playlist_node = ET.SubElement(parent_subnodes, "NODE", TYPE="PLAYLIST", NAME=node_name)
            playlist = ET.SubElement(
                playlist_node, "PLAYLIST",
                ENTRIES=str(len(track_elements)),
                TYPE="LIST",
                UUID=uuid.uuid4().hex
            )
            
            # Add tracks to playlist by mapping TrackID to file path
            for track_elem in track_elements:
                track_id = get_attribute(track_elem, "Key")
                if track_id and track_id in self.track_id_map:
                    file_path = self.track_id_map[track_id]
                    entry = ET.SubElement(playlist, "ENTRY")
                    primary_key = ET.SubElement(entry, "PRIMARYKEY", TYPE="TRACK", KEY=file_path)

    def process_playlists(self, rekordbox_root):
        """
        Process all playlists from Rekordbox XML and convert to NML format.
        
        Args:
            rekordbox_root: Rekordbox XML root element
        """
        # Find PLAYLISTS section in Rekordbox XML
        playlists_section = rekordbox_root.find("PLAYLISTS")
        
        if playlists_section is None:
            # No playlists found, create a default collection playlist
            self.add_default_playlist()
            return
        
        # Create NML PLAYLISTS structure
        nml_root_node = self.add_playlists_section()
        subnodes = ET.SubElement(nml_root_node, "SUBNODES")
        
        # Find ROOT node in Rekordbox playlists
        root_node = playlists_section.find("NODE")
        if root_node is not None:
            # Process all child nodes of ROOT (add them to subnodes)
            child_count = 0
            for node in root_node.findall("NODE"):
                self.process_playlist_node(node, subnodes)
                child_count += 1
            
            subnodes.set("COUNT", str(child_count))
        else:
            # No ROOT node, create default playlist
            self.add_default_playlist()

    def add_default_playlist(self):
        """Create a default collection playlist with all tracks."""
        root_node = self.add_playlists_section()
        subnodes = ET.SubElement(root_node, "SUBNODES", COUNT="1")
        
        playlist_node = ET.SubElement(subnodes, "NODE", TYPE="PLAYLIST", NAME="collection")
        playlist = ET.SubElement(
            playlist_node, "PLAYLIST",
            ENTRIES=str(len(self.tracks)),
            TYPE="LIST",
            UUID=uuid.uuid4().hex
        )
        
        for track_loc in self.tracks:
            entry = ET.SubElement(playlist, "ENTRY")
            primary_key = ET.SubElement(entry, "PRIMARYKEY", TYPE="TRACK", KEY=track_loc)

    def process_track(self, track, collection):
        self.reset_track()

        self.set_track_info(track)
        self.track = self.add_entry(collection)

        self.add_location()
        self.add_album()
        self.add_modification_info()
        self.add_info()
        self.add_tempo()
        self.add_loudness()
        self.add_musical_key()

        self.process_tempo(track)
        self.process_cues(track)

        return True

    def add_head(self):
        head = ET.SubElement(self.root, "HEAD", COMPANY="www.native-instruments.com", PROGRAM="Traktor Pro 4")
        return head

    def add_collection(self, entries):
        collection = ET.SubElement(self.root, "COLLECTION", ENTRIES=str(len(entries)))
        return collection

    def add_sets(self, entries=[]):
        sets = ET.SubElement(self.root, "SETS", ENTRIES=str(len(entries)))
        return sets

    def add_indexing(self):
        indexing = ET.SubElement(self.root, "INDEXING")
        return indexing

    def convert_xml_to_nml(self, xml_file, nml_file):
        tree = ET.parse(xml_file)
        root = tree.getroot()

        self.root = ET.Element("NML", VERSION="20")

        entries = root.findall(".//TRACK")

        self.add_head()
        collection = self.add_collection(entries)

        self.tracks = []
        self.track_id_map = {}

        # Process all tracks and build TrackID -> file path mapping
        for track in entries:
            track_id = get_attribute(track, "TrackID")
            if self.process_track(track, collection):
                loc = get_location(get_attribute(track, "Location"))
                file_path = f"{loc['VOLUME']}{loc['DIR']}{loc['FILE']}"
                self.tracks.append(file_path)
                
                # Map TrackID to file path for playlist processing
                if track_id:
                    self.track_id_map[track_id] = file_path
                
                self.track_index += 1

        self.add_sets()
        # Process playlists from Rekordbox XML
        self.process_playlists(root)
        self.add_indexing()

        tree = ET.ElementTree(self.root)
        tree.write(nml_file, encoding="utf-8", xml_declaration=True, short_empty_elements=False)


if __name__ == "__main__":
    set_conversion("rekordbox", "traktor")
    if len(sys.argv) < 2:
        print("Usage: python rekord_to_nml.py <input.xml> [output.nml]")
        print("  input.xml:  Rekordbox XML collection file")
        print("  output.nml: Optional output NML file (default: input filename with .nml extension)")
        sys.exit(1)
    
    xml_file = sys.argv[1]

    if not exists(xml_file):
        print(f"Error: Input file '{xml_file}' not found.")
        print("Usage: python rekord_to_nml.py <input.xml> [output.nml]")
        sys.exit(1)

    # Use provided output file or generate from input filename
    if len(sys.argv) >= 3:
        nml_file = sys.argv[2]
    else:
        filepath = xml_file.replace(".xml", "").replace(".rekordbox", "")
        nml_file = f"{filepath}.nml"
    
    open(nml_file, "w").close()

    converter = Rekordbox2Traktor()
    converter.convert_xml_to_nml(xml_file, nml_file)

    print(f"{xml_file} was converted to {nml_file}!")