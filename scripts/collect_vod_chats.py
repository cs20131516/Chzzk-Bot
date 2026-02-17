"""
치지직 VOD 채팅 수집 스크립트

사용법:
  # 특정 VOD 테스트
  python scripts/collect_vod_chats.py --vod 12345

  # 채널의 모든 VOD에서 내 채팅 수집
  python scripts/collect_vod_chats.py --channel CHANNEL_ID --my-uid USER_ID_HASH

  # 팔로우 채널 목록에서 수집 (쿠키 필요)
  python scripts/collect_vod_chats.py --follow --my-uid USER_ID_HASH

  # 수동 채널 목록 파일
  python scripts/collect_vod_chats.py --channels-file channels.txt --my-uid USER_ID_HASH
"""

import argparse
import json
import os
import sys
import time
import csv
from pathlib import Path

import requests

BASE_API = "https://api.chzzk.naver.com"
COMM_API = "https://comm-api.game.naver.com"

# 요청 간 딜레이 (429 방지)
PAGE_DELAY = 0.2
VOD_DELAY = 1.0


class ChzzkClient:
    def __init__(self, nid_aut="", nid_ses=""):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://chzzk.naver.com/",
        })
        if nid_aut and nid_ses:
            self.session.cookies.set("NID_AUT", nid_aut, domain=".naver.com")
            self.session.cookies.set("NID_SES", nid_ses, domain=".naver.com")

    def get_json(self, url, params=None):
        """GET 요청 후 JSON 반환, 429/5xx 시 재시도"""
        for attempt in range(5):
            try:
                resp = self.session.get(url, params=params, timeout=15)
                if resp.status_code == 429:
                    wait = float(resp.headers.get("Retry-After", 2))
                    print(f"  [429] Rate limited, waiting {wait}s...")
                    time.sleep(wait)
                    continue
                if resp.status_code >= 500:
                    time.sleep(1 * (attempt + 1))
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as e:
                if attempt == 4:
                    raise
                print(f"  [Retry {attempt+1}] {e}")
                time.sleep(1 * (attempt + 1))
        return None

    # ──────────────────── 내 정보 조회 ────────────────────

    def get_my_info(self):
        """로그인된 유저의 userIdHash 조회 (쿠키 필요)"""
        data = self.get_json(f"{COMM_API}/nng_main/v1/user/getUserStatus")
        if not data or "content" not in data:
            return None
        content = data["content"]
        if not content.get("loggedIn"):
            return None
        return {
            "uid": content.get("userIdHash", ""),
            "nickname": content.get("nickname", ""),
        }

    # ──────────────────── VOD 메타데이터 ────────────────────

    def get_video_info(self, video_no):
        """VOD 메타데이터 조회"""
        data = self.get_json(f"{BASE_API}/service/v2/videos/{video_no}")
        return data.get("content") if data else None

    # ──────────────────── VOD 채팅 수집 ────────────────────

    def get_vod_chats(self, video_no, start_ms=0, end_ms=None, progress=True):
        """VOD의 전체 채팅을 수집하여 리스트로 반환"""
        all_chats = []
        ti = start_ms
        empty_count = 0
        max_empty = 3

        while True:
            url = f"{BASE_API}/service/v1/videos/{video_no}/chats"
            data = self.get_json(url, params={"playerMessageTime": ti})

            if not data or "content" not in data:
                empty_count += 1
                if empty_count >= max_empty:
                    break
                time.sleep(0.5)
                continue

            chats = data["content"].get("videoChats", [])
            if not chats:
                empty_count += 1
                if empty_count >= max_empty:
                    break
                time.sleep(0.5)
                continue

            empty_count = 0

            for chat in chats:
                pm = chat.get("playerMessageTime", 0)
                if end_ms is not None and pm > end_ms:
                    return all_chats

                # 프로필 파싱
                nickname = "알 수 없음"
                try:
                    if chat.get("profile"):
                        profile = json.loads(chat["profile"])
                        nickname = profile.get("nickname", nickname)
                except (json.JSONDecodeError, TypeError):
                    pass

                all_chats.append({
                    "time_ms": pm,
                    "time_str": ms_to_hms(pm),
                    "nickname": nickname,
                    "uid": chat.get("userIdHash", ""),
                    "message": chat.get("content", ""),
                    "extras": chat.get("extras", ""),
                    "msg_type": chat.get("messageTypeCode", 0),
                })

            last_time = chats[-1].get("playerMessageTime", ti)
            if last_time <= ti:
                ti = last_time + 1
            else:
                ti = last_time + 1

            if progress:
                print(f"\r  채팅 {len(all_chats)}개 수집중... (time={ms_to_hms(ti)})", end="", flush=True)

            time.sleep(PAGE_DELAY)

        if progress:
            print()
        return all_chats

    # ──────────────────── 채널 VOD 목록 ────────────────────

    def get_channel_videos(self, channel_id, max_pages=50):
        """채널의 VOD 목록 조회 (최신순)"""
        videos = []
        page = 0
        while page < max_pages:
            data = self.get_json(
                f"{BASE_API}/service/v1/channels/{channel_id}/videos",
                params={"sortType": "LATEST", "pagingType": "PAGE", "page": page, "size": 50},
            )
            if not data or "content" not in data:
                break

            content = data["content"]
            page_data = content.get("data", [])
            if not page_data:
                break

            for v in page_data:
                videos.append({
                    "video_no": v.get("videoNo"),
                    "title": v.get("videoTitle", ""),
                    "duration": v.get("duration", 0),
                    "publish_date": v.get("publishDate", ""),
                })

            # 다음 페이지 확인
            total_pages = content.get("totalPages", 0)
            page += 1
            if page >= total_pages:
                break
            time.sleep(0.3)

        return videos

    # ──────────────────── 팔로우 목록 ────────────────────

    def get_following_channels(self):
        """팔로우 채널 목록 조회 (쿠키 필요)"""
        channels = []
        page = 0
        while True:
            data = self.get_json(
                f"{BASE_API}/service/v1/channels/followings",
                params={"page": page, "size": 50},
            )
            if not data or "content" not in data:
                break

            content = data["content"]
            following_list = content.get("followingList", [])
            if not following_list:
                break

            for item in following_list:
                ch = item.get("channel", {})
                channels.append({
                    "channel_id": ch.get("channelId", ""),
                    "channel_name": ch.get("channelName", ""),
                })

            total_pages = content.get("totalPages", 1)
            page += 1
            if page >= total_pages:
                break
            time.sleep(0.3)

        return channels


# ──────────────────── 유틸리티 ────────────────────

def ms_to_hms(ms):
    total_sec = ms // 1000
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    s = total_sec % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def filter_my_chats(all_chats, my_uid):
    """특정 유저의 채팅만 필터링하고, 직전 맥락 포함"""
    my_chats = []
    for i, chat in enumerate(all_chats):
        if chat["uid"] == my_uid:
            # 직전 맥락 (최대 10개)
            context_start = max(0, i - 10)
            context = all_chats[context_start:i]
            my_chats.append({
                "context": [
                    {"nickname": c["nickname"], "message": c["message"], "time": c["time_str"]}
                    for c in context
                ],
                "response": {
                    "nickname": chat["nickname"],
                    "message": chat["message"],
                    "time": chat["time_str"],
                },
            })
    return my_chats


def save_results(data, output_path):
    """결과 저장 (JSONL 형식)"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"저장 완료: {output_path} ({len(data)}개)")


def save_raw_chats_csv(chats, output_path):
    """전체 채팅을 CSV로 저장"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["time_str", "nickname", "uid", "message"])
        writer.writeheader()
        for chat in chats:
            writer.writerow({
                "time_str": chat["time_str"],
                "nickname": chat["nickname"],
                "uid": chat["uid"],
                "message": chat["message"],
            })

    print(f"CSV 저장 완료: {output_path} ({len(chats)}개)")


# ──────────────────── 메인 ────────────────────

def main():
    parser = argparse.ArgumentParser(description="치지직 VOD 채팅 수집")

    # 소스 선택 (상호 배타)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--vod", type=int, help="단일 VOD 번호 테스트")
    source.add_argument("--channel", type=str, help="채널 ID")
    source.add_argument("--follow", action="store_true", help="팔로우 채널에서 수집")
    source.add_argument("--channels-file", type=str, help="채널 ID 목록 파일 (한 줄에 하나)")

    # 필터링
    parser.add_argument("--my-uid", type=str, help="내 userIdHash (필터링용)")

    # 출력
    parser.add_argument("--output-dir", type=str, default="data/vod_chats", help="출력 디렉토리")
    parser.add_argument("--save-raw", action="store_true", help="전체 채팅도 CSV로 저장")
    parser.add_argument("--max-vods", type=int, default=10, help="채널당 최대 VOD 수")

    args = parser.parse_args()

    # .env에서 쿠키 로드
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    nid_aut = os.getenv("NID_AUT", "")
    nid_ses = os.getenv("NID_SES", "")

    client = ChzzkClient(nid_aut, nid_ses)

    # ── 쿠키로 내 UID 자동 조회 ──
    if not args.my_uid and nid_aut:
        print("쿠키로 내 정보 조회중...")
        my_info = client.get_my_info()
        if my_info:
            args.my_uid = my_info["uid"]
            print(f"  닉네임: {my_info['nickname']}")
            print(f"  UID: {my_info['uid']}")
            print()
        else:
            print("  쿠키가 만료되었거나 로그인 정보를 가져올 수 없습니다.")
            print("  --my-uid 옵션으로 직접 지정하거나, 봇을 실행하여 재로그인하세요.")
            print()

    # ── 단일 VOD 테스트 ──
    if args.vod:
        print(f"VOD #{args.vod} 정보 조회중...")
        info = client.get_video_info(args.vod)
        if not info:
            print("VOD를 찾을 수 없습니다.")
            return

        title = info.get("videoTitle", "제목없음")
        duration = info.get("duration", 0)
        channel_name = info.get("channel", {}).get("channelName", "")
        print(f"  채널: {channel_name}")
        print(f"  제목: {title}")
        print(f"  길이: {ms_to_hms(duration * 1000)}")
        print()

        print("채팅 수집중...")
        chats = client.get_vod_chats(args.vod)
        print(f"총 {len(chats)}개 채팅 수집 완료")

        if args.save_raw:
            save_raw_chats_csv(chats, f"{args.output_dir}/raw/vod_{args.vod}.csv")

        if args.my_uid:
            my_chats = filter_my_chats(chats, args.my_uid)
            print(f"내 채팅: {len(my_chats)}개")
            if my_chats:
                save_results(my_chats, f"{args.output_dir}/my_chats/vod_{args.vod}.jsonl")
                # 미리보기
                print("\n── 미리보기 (최대 3개) ──")
                for item in my_chats[:3]:
                    ctx = " | ".join(f"{c['nickname']}: {c['message']}" for c in item["context"][-3:])
                    print(f"  맥락: {ctx}")
                    print(f"  내 응답: {item['response']['message']}")
                    print()
        else:
            # UID 없으면 전체 저장
            save_raw_chats_csv(chats, f"{args.output_dir}/raw/vod_{args.vod}.csv")
            # 유니크 유저 목록 출력
            users = {}
            for c in chats:
                uid = c["uid"]
                if uid not in users:
                    users[uid] = {"nickname": c["nickname"], "count": 0}
                users[uid]["count"] += 1
            print(f"\n유니크 유저: {len(users)}명")
            print("── 채팅 많은 상위 20명 ──")
            for uid, info in sorted(users.items(), key=lambda x: -x[1]["count"])[:20]:
                print(f"  {info['nickname']:20s}  ({info['count']:4d}개)  uid={uid}")
            print("\n위 목록에서 본인의 uid를 찾아 --my-uid 옵션으로 다시 실행하세요.")

        return

    # ── 채널 목록 구성 ──
    channels = []

    if args.channel:
        channels = [{"channel_id": args.channel, "channel_name": "지정 채널"}]

    elif args.follow:
        if not nid_aut:
            print("팔로우 목록 조회에는 NID_AUT/NID_SES 쿠키가 필요합니다.")
            print(".env 파일에 설정하거나 봇을 한번 실행하여 로그인하세요.")
            return
        print("팔로우 채널 목록 조회중...")
        channels = client.get_following_channels()
        if not channels:
            print("팔로우 채널이 없거나 쿠키가 만료되었습니다.")
            return
        print(f"팔로우 채널: {len(channels)}개")
        for ch in channels:
            print(f"  - {ch['channel_name']} ({ch['channel_id'][:8]}...)")
        print()

    elif args.channels_file:
        file_path = Path(args.channels_file)
        if not file_path.exists():
            print(f"파일을 찾을 수 없습니다: {file_path}")
            return
        with open(file_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    channels.append({"channel_id": line, "channel_name": ""})
        print(f"채널 {len(channels)}개 로드")

    if not args.my_uid:
        print("경고: --my-uid가 지정되지 않았습니다. 전체 채팅만 저장됩니다.")

    # ── 채널별 VOD 수집 ──
    total_my_chats = 0
    for ch in channels:
        ch_id = ch["channel_id"]
        ch_name = ch["channel_name"]
        print(f"\n{'='*60}")
        print(f"채널: {ch_name} ({ch_id[:8]}...)")
        print(f"{'='*60}")

        videos = client.get_channel_videos(ch_id, max_pages=5)
        if not videos:
            print("  VOD 없음")
            continue

        print(f"  VOD {len(videos)}개 발견 (최대 {args.max_vods}개 처리)")

        for vid in videos[:args.max_vods]:
            vno = vid["video_no"]
            print(f"\n  VOD #{vno}: {vid['title'][:40]}")
            print(f"  길이: {ms_to_hms(vid['duration'] * 1000)}  날짜: {vid['publish_date'][:10]}")

            chats = client.get_vod_chats(vno)
            if not chats:
                print("    채팅 없음")
                continue

            print(f"    총 {len(chats)}개 채팅")

            if args.save_raw:
                safe_name = ch_name.replace("/", "_").replace("\\", "_")[:20]
                save_raw_chats_csv(chats, f"{args.output_dir}/raw/{safe_name}/vod_{vno}.csv")

            if args.my_uid:
                my_chats = filter_my_chats(chats, args.my_uid)
                if my_chats:
                    safe_name = ch_name.replace("/", "_").replace("\\", "_")[:20]
                    save_results(my_chats, f"{args.output_dir}/my_chats/{safe_name}/vod_{vno}.jsonl")
                    total_my_chats += len(my_chats)
                    print(f"    내 채팅: {len(my_chats)}개")
                else:
                    print(f"    내 채팅: 0개 (이 VOD에서 활동 없음)")

            time.sleep(VOD_DELAY)

    if args.my_uid:
        print(f"\n{'='*60}")
        print(f"수집 완료! 총 내 채팅: {total_my_chats}개")
        print(f"저장 위치: {args.output_dir}/my_chats/")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
