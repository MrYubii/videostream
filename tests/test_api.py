import pytest


def register_consumer(client, username="consumer_test"):
    return client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "ConsumerPass1!", "full_name": "Test Consumer"},
    )


def login(client, username, password):
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


class TestAuth:
    def test_consumer_signup_and_login(self, client):
        res = register_consumer(client, "dave")
        assert res.status_code == 201
        body = res.json()
        assert body["username"] == "dave"
        assert body["role"] == "consumer"

        login_res = client.post("/api/auth/login", json={"username": "dave", "password": "ConsumerPass1!"})
        assert login_res.status_code == 200
        assert login_res.json()["role"] == "consumer"

    def test_duplicate_username_conflict(self, client):
        register_consumer(client, "bob")
        res = register_consumer(client, "bob")
        assert res.status_code == 409

    def test_bad_password_rejected(self, client):
        res = client.post("/api/auth/login", json={"username": "alice", "password": "wrong-password"})
        assert res.status_code == 401

    def test_me_requires_token(self, client):
        assert client.get("/api/auth/me").status_code == 401
        token = login(client, "alice", "ConsumerPass1!")
        res = client.get("/api/auth/me", headers=auth(token))
        assert res.status_code == 200
        assert res.json()["username"] == "alice"


class TestAdminCreators:
    def test_admin_creates_creator(self, client):
        token = login(client, "admin_seed", "AdminPass123!")
        res = client.post(
            "/api/admin/creators",
            json={"username": "creator_new", "email": "creator_new@example.com", "password": "CreatorPass9!"},
            headers=auth(token),
        )
        assert res.status_code == 201
        assert res.json()["role"] == "creator"

    def test_consumer_cannot_access_admin(self, client):
        token = login(client, "alice", "ConsumerPass1!")
        assert client.get("/api/admin/creators", headers=auth(token)).status_code == 403
        res = client.post(
            "/api/admin/creators",
            json={"username": "creator_y", "email": "creator_y@example.com", "password": "CreatorPass9!"},
            headers=auth(token),
        )
        assert res.status_code == 403

    def test_admin_disables_and_reenables_creator(self, client):
        admin_token = login(client, "admin_seed", "AdminPass123!")
        creators = client.get("/api/admin/creators", headers=auth(admin_token)).json()
        target = next(c for c in creators if c["username"] == "creator_x")
        res = client.patch(f"/api/admin/creators/{target['id']}", json={"is_active": False}, headers=auth(admin_token))
        assert res.status_code == 200
        assert res.json()["is_active"] is False

        res = client.patch(f"/api/admin/creators/{target['id']}", json={"is_active": True}, headers=auth(admin_token))
        assert res.status_code == 200
        assert res.json()["is_active"] is True


class TestVideos:
    def test_consumer_cannot_upload(self, client):
        token = login(client, "alice", "ConsumerPass1!")
        res = client.post(
            "/api/videos",
            data={"title": "Nope", "publisher": "Nope", "genre": "Film", "age_rating": "U"},
            files={"file": ("nope.mp4", b"not-a-video", "video/mp4")},
            headers=auth(token),
        )
        assert res.status_code == 403

    def test_creator_upload_and_process(self, client, sample_video):
        token = login(client, "creator_x", "CreatorPass9!")
        with open(sample_video, "rb") as fh:
            res = client.post(
                "/api/videos",
                data={
                    "title": "Test Clip",
                    "publisher": "Test Studio",
                    "producer": "T. Qa",
                    "genre": "Film",
                    "age_rating": "12",
                    "description": "A test upload",
                },
                files={"file": ("clip.mp4", fh, "video/mp4")},
                headers=auth(token),
            )
        assert res.status_code == 201, res.text
        video = res.json()
        assert video["status"] == "processing"

        detail = client.get(f"/api/videos/{video['id']}").json()
        assert detail["title"] == "Test Clip"
        assert detail["age_rating"] == "12"
        assert detail["status"] == "ready"
        assert detail["duration_seconds"] >= 1
        assert detail["thumbnail_url"]

    def test_dashboard_and_search(self, client):
        data = client.get("/api/videos", params={"search": "Test Clip"}).json()
        assert data["total"] >= 1
        item = data["items"][0]
        assert item["genre"] == "Film"

        filtered = client.get("/api/videos", params={"genre": "Film", "age_rating": "12"}).json()
        assert all(v["genre"] == "Film" and v["age_rating"] == "12" for v in filtered["items"])

    def test_stream_with_range(self, client, sample_video):
        video_id = client.get("/api/videos", params={"search": "Test Clip"}).json()["items"][0]["id"]

        full = client.get(f"/api/videos/{video_id}/stream")
        assert full.status_code == 200
        assert full.headers["content-type"] == "video/mp4"

        ranged = client.get(f"/api/videos/{video_id}/stream", headers={"Range": "bytes=0-99"})
        assert ranged.status_code == 206
        assert len(ranged.content) == 100
        assert ranged.headers["content-range"].startswith("bytes 0-99/")

        missing = client.get("/api/videos/999999/stream")
        assert missing.status_code == 404

    def test_unsupported_format_rejected(self, client):
        token = login(client, "creator_x", "CreatorPass9!")
        res = client.post(
            "/api/videos",
            data={"title": "Bad", "publisher": "X", "genre": "Film", "age_rating": "U"},
            files={"file": ("evil.txt", b"plain text", "text/plain")},
            headers=auth(token),
        )
        assert res.status_code == 415


class TestCommentsAndRatings:
    def _video_id(self, client):
        return client.get("/api/videos", params={"search": "Test Clip"}).json()["items"][0]["id"]

    def test_comment_requires_auth(self, client):
        assert client.post(f"/api/videos/{self._video_id(client)}/comments", json={"body": "hi"}).status_code == 401

    def test_add_and_list_comments(self, client):
        video_id = self._video_id(client)
        token = login(client, "alice", "ConsumerPass1!")
        res = client.post(
            f"/api/videos/{video_id}/comments",
            json={"body": "Great clip!"},
            headers=auth(token),
        )
        assert res.status_code == 201
        assert res.json()["author"] == "alice"

        comments = client.get(f"/api/videos/{video_id}/comments").json()
        assert any(c["body"] == "Great clip!" for c in comments)

    def test_rate_video(self, client):
        video_id = self._video_id(client)
        token = login(client, "alice", "ConsumerPass1!")

        rating = client.put(f"/api/videos/{video_id}/rating", json={"value": 5}, headers=auth(token))
        assert rating.status_code == 200
        assert rating.json()["user_rating"] == 5
        assert rating.json()["average"] == 5.0

        rating = client.put(f"/api/videos/{video_id}/rating", json={"value": 1}, headers=auth(token))
        assert rating.json()["user_rating"] == 1
        assert rating.json()["average"] == 1.0

        got = client.get(f"/api/videos/{video_id}/rating").json()
        assert got["count"] >= 1

        bad = client.put(f"/api/videos/{video_id}/rating", json={"value": 99}, headers=auth(token))
        assert bad.status_code == 422


class TestReactions:
    def _video_id(self, client):
        return client.get("/api/videos", params={"search": "Test Clip"}).json()["items"][0]["id"]

    def test_reaction_requires_auth(self, client):
        assert client.put(f"/api/videos/{self._video_id(client)}/reaction", json={"reaction": "like"}).status_code == 401

    def test_like_and_dislike(self, client):
        video_id = self._video_id(client)
        token = login(client, "alice", "ConsumerPass1!")

        r = client.put(f"/api/videos/{video_id}/reaction", json={"reaction": "like"}, headers=auth(token))
        assert r.status_code == 200
        body = r.json()
        assert body["like_count"] == 1
        assert body["dislike_count"] == 0
        assert body["user_reaction"] == "like"

        r = client.put(f"/api/videos/{video_id}/reaction", json={"reaction": "dislike"}, headers=auth(token))
        body = r.json()
        assert body["like_count"] == 0
        assert body["dislike_count"] == 1
        assert body["user_reaction"] == "dislike"

        r = client.put(f"/api/videos/{video_id}/reaction", json={"reaction": None}, headers=auth(token))
        body = r.json()
        assert body["like_count"] == 0
        assert body["dislike_count"] == 0
        assert body["user_reaction"] is None

    def test_reaction_counts_in_video_detail(self, client):
        video_id = self._video_id(client)
        token = login(client, "alice", "ConsumerPass1!")
        client.put(f"/api/videos/{video_id}/reaction", json={"reaction": "like"}, headers=auth(token))
        detail = client.get(f"/api/videos/{video_id}").json()
        assert detail["like_count"] == 1
        assert detail["dislike_count"] == 0


class TestRangeStreaming:
    def _upload_clip(self, client, sample_video, title="Range Clip"):
        token = login(client, "creator_x", "CreatorPass9!")
        with open(sample_video, "rb") as fh:
            res = client.post(
                "/api/videos",
                data={"title": title, "publisher": "S", "genre": "Film", "age_rating": "U"},
                files={"file": ("clip.mp4", fh, "video/mp4")},
                headers=auth(token),
            )
        assert res.status_code == 201, res.text
        return res.json()["id"]

    def test_empty_age_rating_param_ok(self, client):
        res = client.get("/api/videos", params={"search": "", "genre": "", "age_rating": "", "sort": "latest", "offset": 0, "limit": 12})
        assert res.status_code == 200

    def test_search_wildcard_is_escaped(self, client):
        res = client.get("/api/videos", params={"search": "%"})
        assert res.status_code == 200
        assert all("%" not in (v["title"] or "") and "%" not in (v["publisher"] or "") for v in res.json()["items"])

    def test_suffix_range(self, client, sample_video):
        vid = self._upload_clip(client, sample_video, "Suffix Clip")
        r = client.get(f"/api/videos/{vid}/stream", headers={"Range": "bytes=-100"})
        assert r.status_code == 206
        assert len(r.content) == 100

    def test_out_of_bounds_range_416(self, client, sample_video):
        vid = self._upload_clip(client, sample_video, "Oob Clip")
        r = client.get(f"/api/videos/{vid}/stream", headers={"Range": "bytes=999999999-"})
        assert r.status_code == 416

    def test_reversed_range_416(self, client, sample_video):
        vid = self._upload_clip(client, sample_video, "Rev Clip")
        r = client.get(f"/api/videos/{vid}/stream", headers={"Range": "bytes=100-50"})
        assert r.status_code == 416

    def test_malformed_range_ignored(self, client, sample_video):
        vid = self._upload_clip(client, sample_video, "Mal Clip")
        r = client.get(f"/api/videos/{vid}/stream", headers={"Range": "bytes=abc"})
        assert r.status_code == 200

    def test_view_count_not_inflated_by_range_requests(self, client, sample_video):
        vid = self._upload_clip(client, sample_video, "View Clip")
        before = client.get(f"/api/videos/{vid}").json()["view_count"]
        for _ in range(4):
            client.get(f"/api/videos/{vid}/stream", headers={"Range": "bytes=0-99"})
        after = client.get(f"/api/videos/{vid}").json()["view_count"]
        assert after - before <= 1


class TestVideoManagement:
    def test_owner_patches_and_deletes(self, client, sample_video):
        token = login(client, "creator_x", "CreatorPass9!")
        with open(sample_video, "rb") as fh:
            up = client.post(
                "/api/videos",
                data={"title": "Edit Me", "publisher": "P", "genre": "Film", "age_rating": "U"},
                files={"file": ("e.mp4", fh, "video/mp4")},
                headers=auth(token),
            ).json()
        vid = up["id"]

        r = client.patch(f"/api/videos/{vid}", json={"title": "Edited Title", "age_rating": "15"}, headers=auth(token))
        assert r.status_code == 200
        assert r.json()["title"] == "Edited Title"
        assert r.json()["age_rating"] == "15"

        r = client.delete(f"/api/videos/{vid}", headers=auth(token))
        assert r.status_code == 204
        assert client.get(f"/api/videos/{vid}").status_code == 404

    def test_non_owner_cannot_manage(self, client, sample_video):
        owner = login(client, "creator_x", "CreatorPass9!")
        with open(sample_video, "rb") as fh:
            vid = client.post(
                "/api/videos",
                data={"title": "Locked", "publisher": "P", "genre": "Film", "age_rating": "U"},
                files={"file": ("l.mp4", fh, "video/mp4")},
                headers=auth(owner),
            ).json()["id"]
        alice = login(client, "alice", "ConsumerPass1!")
        assert client.patch(f"/api/videos/{vid}", json={"title": "x"}, headers=auth(alice)).status_code == 403
        assert client.delete(f"/api/videos/{vid}", headers=auth(alice)).status_code == 403

    def test_admin_can_delete_any(self, client, sample_video):
        owner = login(client, "creator_x", "CreatorPass9!")
        with open(sample_video, "rb") as fh:
            vid = client.post(
                "/api/videos",
                data={"title": "Admins Too", "publisher": "P", "genre": "Film", "age_rating": "U"},
                files={"file": ("a.mp4", fh, "video/mp4")},
                headers=auth(owner),
            ).json()["id"]
        adm = login(client, "admin_seed", "AdminPass123!")
        assert client.delete(f"/api/videos/{vid}", headers=auth(adm)).status_code == 204


class TestAuthSecurity:
    def test_case_insensitive_duplicate_username_conflict(self, client):
        client.post("/api/auth/register", json={"username": "CaseUser", "email": "case@example.com", "password": "ConsumerPass1!"})
        res = client.post("/api/auth/register", json={"username": "caseuser", "email": "case2@example.com", "password": "ConsumerPass1!"})
        assert res.status_code == 409

    def test_admin_cannot_grant_admin_role(self, client):
        adm = login(client, "admin_seed", "AdminPass123!")
        creators = client.get("/api/admin/creators", headers=auth(adm)).json()
        target = next(c for c in creators if c["username"] == "creator_x")
        res = client.patch(f"/api/admin/creators/{target['id']}", json={"role": "admin"}, headers=auth(adm))
        assert res.status_code == 400

    def test_admin_stats(self, client):
        adm = login(client, "admin_seed", "AdminPass123!")
        r = client.get("/api/admin/stats", headers=auth(adm))
        assert r.status_code == 200
        body = r.json()
        assert body["total_creators"] >= 1
        assert body["total_videos"] >= 1


class TestStaticFrontend:
    def test_index_served(self, client):
        res = client.get("/")
        assert res.status_code == 200
        assert "VideoStream" in res.text

    def test_assets_served(self, client):
        assert client.get("/css/style.css").status_code == 200
        assert client.get("/js/app.js").status_code == 200
        assert client.get("/video.html").status_code == 200
        assert client.get("/admin.html").status_code == 200
        assert client.get("/favicon.svg").status_code == 200

    def test_openapi_docs(self, client):
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200
