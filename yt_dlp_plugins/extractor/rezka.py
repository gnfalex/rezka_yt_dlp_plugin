# ⚠ Don't use relative imports
from yt_dlp.extractor.common import InfoExtractor
import re, json
import os, base64
import time
import urllib.parse

from yt_dlp.utils import (
    get_elements_by_attribute,
    get_element_html_by_attribute,
    get_elements_html_by_attribute,
    render_table, extract_attributes,
    js_to_json
)

def split_rezka (inStr):
    if not inStr: return []
    result = []
    for entry in inStr.split(","):
        idx = entry.index("]")
        for url_data in entry[idx+1:].split(" or "):
            result.append ({
              "name": entry[1:idx],
              "url": url_data,
              "ext": os.path.splitext(url_data)[1][1:]
            })
    return result

def num_list (inArr):
    a = ([int(x) for x in set(inArr)])
    a.sort()
    tmp = outStr = str(a[i])
    i = 1
    while i < len (a):
        if a[i] != a[i-1]+1:
            if tmp != a[i-1]: outStr += f"-{a[i-1]}"
            outStr += f",{a[i]}"
            tmp = a[i]
        i += 1
    if tmp != a[i-1]: outStr += ("-" if a[i-1] == a[i-2]+1 else ",") + str(a[i-1])
    return outStr

def decode_rezka (inStr):
    if not inStr: return []
    bk= [
        "$$#!!@#!@##",
        "^^^!@##!!##",
        "####^!!##!@@",
        "@@@@@!##!^^^",
        "$$!!@$$@^!@#$$@"
    ]
    fs = "//_//"
    tmpStr = inStr[2:]
    for bx in bk:
        tmpStr = tmpStr.replace(fs + base64.b64encode(bx.encode()).decode(),"")
    tmpStr = base64.b64decode(tmpStr).decode()
    return split_rezka(tmpStr)

def parse_episodes (inStr):
    result = {}
    episodesStr = inStr.replace(" active", "")
    for episode in get_elements_html_by_attribute("class", "b-simple_episode__item", episodesStr):
        attrs = extract_attributes(episode)
        s_id = attrs.get("data-season_id", "0")
        e_id = attrs.get("data-episode_id", "0")
        if not s_id in result: result[s_id]=[]
        result[s_id].append(e_id)
    return result

def rezka_dict(info):
    result = {}
    _FORMATS = {
        "360p" : {"w":360, "h":240},
        "480p" : {"w":480, "h":360},
        "720p" : {"w":720, "h":480},
        "1080p": {"w":1080,"h":720},
        "1080p Ultra" : {"w":2160,"h":1440}
    }
    formats = []
    subtitles = {}
    for format_data in (decode_rezka(info.get("streams")) + decode_rezka(info.get("url"))):
        formats.append({
            "format":format_data.get("name"),
            "format_id": format_data.get("name"),
            "format_note": urllib.parse.urlparse(format_data.get("url")).hostname,
            "url":format_data.get("url"),
            "ext": "mp4",
            "container":format_data.get("ext"),
            "width":traverse_obj(_FORMATS, (format_data.get("name"),"w"), 0),
            "height":traverse_obj(_FORMATS,(format_data.get("name"),"h"), 0),
            "preference": -2 if format_data.get("ext")=="m3u8" else -1
        })
    for sub_data in split_rezka(info.get("subtitle")):
        sub_code = traverse_obj(info, ("subtitle_lns", sub_data.get("name")), "zz")
        if not sub_code in subtitles:
            subtitles[sub_code]=[]
        subtitles[sub_code].append(sub_data)
    if formats: result["formats"]=formats
    if subtitles: result["subtitles"]=subtitles
    return result

class RezkaIE(InfoExtractor):
    _WORKING = True
    _VALID_URL = r'^https?://h?d?rezka\..*/(?P<id>\d+)-(?P<name>[^/]+)-(?P<year>\d+)\.html.*'
    _SCRIPT_REGEX = r'initCDN(Movies|Series)Events\(([^;]*})\);'
    _DICT_HEADERS = ["id","translator_id", "camrip", "ads", "director", "domain", "unknown1", "info"]
    _DOMAIN = ""
    
    def call_rezkaAPI (self, domain, data, action):
        postdata = {x:int(data.get(x, 0)) for x in ["id", "translator_id"]}
        postdata.update ({"is_"+x:int(data.get(x, 0)) for x in ["camrip","ads","director"]})
        postdata.update({"action":action})
        url =  f'https://{domain}/ajax/get_cdn_series/?t={str(int(1000*(time.time())))}'
        #url = 
        vid = f'{postdata.get("id", 0)}_{postdata.get("translator_id", 0)}'
        if "season" in data:
            postdata.update({x:data[x] for x in ["season", "episode"]})
            vid = vid + f'_{data["season"]}_{data["episode"]}'
        time.sleep(1)
        return self._download_json(
            url,
            video_id = vid,
            data = urllib.parse.urlencode(postdata).encode("utf8")
        )

    def _real_extract(self, url):
        video_id = self._match_id(url)
        webpage = self._download_webpage (url, video_id)
        video_title = " _ ".join([re.sub(r'\s*<[^>]*>\s*','',x) for x in get_elements_by_attribute("class","b-post__title", webpage, tag = "div")])
        video_alttitle = " _ ".join(get_elements_by_attribute("class","b-post__origtitle", webpage, tag = "div"))
        video_alttitle = video_alttitle if video_alttitle else video_title
        
        translationList = get_elements_html_by_attribute("class", "b-translator__item active", webpage, tag = "li") + get_elements_html_by_attribute("class", "b-translator__item", webpage, tag = "li")
        scriptRegex = re.compile (self._SCRIPT_REGEX)
        scriptData = scriptRegex.search(webpage)
        if not scriptData:
            self.report_error("Cant find scriptData")
            return {}
        video_type = scriptData.group(1)
        scriptData = dict(zip(self._DICT_HEADERS ,json.loads("["+scriptData.group(2).replace("'",'"')+"]")))
        self._DOMAIN = scriptData.get("domain", urllib.parse.urlparse(url).hostname)
        if not translationList:
            return {**{
                "_type":"video",
                "id":video_id,
                "title": video_title,
                "alt_title": video_alttitle
              }, **rezka_dict(scriptData)}
        else:
            trDict = {}
            for tr in translationList:
                trInfo = {key.replace("data-",""):val for key,val in extract_attributes(tr).items()}
                if not "id" in trInfo: trInfo["id"]= video_id
                trDict[trInfo["translator_id"]]=trInfo
                if video_type == "Series":
                        json_resp = self.call_rezkaAPI (
                            domain = self._DOMAIN,
                            data = trInfo,
                            action = "get_episodes")
                        trInfo["episodes"]= parse_episodes (json_resp["episodes"])
                        trInfo["episodesStr"]=", ".join([f's{season}e[{num_list(episodes)}]' for season, episodes in trInfo["episodes"].items()])
            while True:
                self.report_warning("Select translation")
                if video_type == "Series":
                    print(render_table(["ID","\tName","\tEpisodes"], [[trId, trDict[trId].get("title"), trDict[trId].get("episodesStr") ] for trId in trDict]))
                else:
                    print(render_table(["ID","\tName"], [[trId, trDict[trId].get("title")] for trId in trDict]))
                trIdx = input("Enter translator ID:")
                if trIdx in trDict: break
            if video_type == "Series":
                out = {
                    "_type":"playlist",
                    "id":video_id,
                    "title":video_title,
                    "alt_title": video_alttitle,
                    "entries":[]
                }
                for season, episodes in trDict[trIdx]["episodes"].items():
                    for episode in episodes:
                        json_resp = self.call_rezkaAPI (
                            domain = self._DOMAIN,
                            data = {**trDict[trIdx], **{"season": season, "episode": episode}},
                            action = "get_stream"
                        )
                        out["entries"].append({**{
                            "_type":"video",
                            "id":video_id,
                            "title": f"s{int(season):02d}e{int(episode):02d} {video_title}",
                            "alt_title": video_alttitle
                        }, **rezka_dict(json_resp)})
                        
                return out
            else:
                json_resp = call_rezkaAPI(
                    domain = self._DOMAIN,
                    data = trDict[trIdx],
                    action = "get_movie"
                )
                return {**{
                        "_type":"video",
                        "id":video_id,
                        "title": video_title,
                        "alt_title": video_alttitle
                    }, **rezka_dict(json_resp)}