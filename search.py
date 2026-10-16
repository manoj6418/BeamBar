# Standard Library
import json
import logging
import re
from urllib.parse import quote_plus

# Third Party Library
import requests

log = logging.getLogger('beambar.search')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17 Safari/605.1.15',
    'Accept-Language': 'en-IN,en;q=0.9',
}
TMDB_IMAGE = 'https://image.tmdb.org/t/p/w185'
INITIAL_DATA = re.compile(r'var ytInitialData = (\{.*?\});</script>', re.S)


def youtube(query, limit=6):
    try:
        html = requests.get(
            f'https://www.youtube.com/results?search_query={quote_plus(query)}', headers=HEADERS, timeout=8
        ).text
    except requests.RequestException as exc:
        log.warning('youtube search failed: %s', exc)
        return []
    match = INITIAL_DATA.search(html)
    if not match:
        return []
    results = []

    def walk(node):
        if len(results) >= limit:
            return
        if isinstance(node, dict):
            video = node.get('videoRenderer')
            if video and video.get('videoId'):
                title = ''.join(run.get('text', '') for run in video.get('title', {}).get('runs', []))
                channel = ''.join(run.get('text', '') for run in video.get('ownerText', {}).get('runs', []))
                length = video.get('lengthText', {}).get('simpleText', '')
                thumbs = video.get('thumbnail', {}).get('thumbnails', [])
                results.append(
                    {
                        'kind': 'youtube',
                        'title': title,
                        'subtitle': ' · '.join(part for part in (channel, length) if part),
                        'image': thumbs[-1]['url'] if thumbs else None,
                        'link': f"https://www.youtube.com/watch?v={video['videoId']}",
                    }
                )
                return
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    try:
        walk(json.loads(match.group(1)))
    except ValueError:
        return []
    return results


def tmdb(query, api_key, limit=6):
    if not api_key:
        return []
    try:
        data = requests.get(
            'https://api.themoviedb.org/3/search/multi',
            params={'api_key': api_key, 'query': query, 'include_adult': 'false'},
            headers=HEADERS,
            timeout=8,
        ).json()
    except (requests.RequestException, ValueError) as exc:
        log.warning('tmdb search failed: %s', exc)
        return []
    results = []
    for item in data.get('results', []):
        if item.get('media_type') not in ('movie', 'tv'):
            continue
        title = item.get('title') or item.get('name') or ''
        year = (item.get('release_date') or item.get('first_air_date') or '')[:4]
        results.append(
            {
                'kind': item['media_type'],
                'title': title,
                'subtitle': ' · '.join(
                    part for part in (('Movie' if item['media_type'] == 'movie' else 'Series'), year) if part
                ),
                'image': TMDB_IMAGE + item['poster_path'] if item.get('poster_path') else None,
                'netflix': f'https://www.netflix.com/search?q={quote_plus(title)}',
                'prime': f'https://app.primevideo.com/search?phrase={quote_plus(title)}',
                'link': f'https://www.youtube.com/results?search_query={quote_plus(title + " trailer")}',
            }
        )
        if len(results) >= limit:
            break
    return results


def search(query, api_key=None):
    return tmdb(query, api_key, limit=4) + youtube(query, limit=6)
