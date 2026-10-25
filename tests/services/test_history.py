import sqlite3
import threading

from matnyab.api import HistoryItem
from matnyab.services import create_history_store


def item(i, created=None, text="x"):
    return HistoryItem(f"id{i}", f"s{i}.png", created or f"2026-01-01T00:00:{i % 60:02d}", text, "raw", 90.5)


def test_add_list_newest_first_and_fields(tmp_path):
    st = create_history_store(tmp_path / "h.db")
    st.add(item(1, "2026-01-01T00:00:01", "متن"))
    st.add(item(2, "2026-01-03T00:00:00"))
    st.add(item(3, "2026-01-02T00:00:00"))
    got = st.list()
    assert [i.id for i in got] == ["id2", "id3", "id1"]
    assert got[2] == HistoryItem("id1", "s1.png", "2026-01-01T00:00:01", "متن", "raw", 90.5)
    assert [i.id for i in st.list(2)] == ["id2", "id3"]
    assert st.list(0) == []


def test_ties_use_insertion_order_newest_first(tmp_path):
    st = create_history_store(tmp_path / "h.db")
    for i in range(3):
        st.add(item(i, "2026-01-01T00:00:00"))
    assert [i.id for i in st.list()] == ["id2", "id1", "id0"]


def test_cap_200_trims_oldest(tmp_path):
    st = create_history_store(tmp_path / "h.db")
    for i in range(230):
        st.add(HistoryItem(f"i{i}", "s", f"2026-01-01T{i // 3600:02d}:{(i // 60) % 60:02d}:{i % 60:02d}", "t", "lex", 1.0))
    got = st.list()
    assert len(got) == 200
    assert got[0].id == "i229" and got[-1].id == "i30"


def test_text_cap_truncates_without_marker(tmp_path):
    st = create_history_store(tmp_path / "h.db")
    st.add(item(1, text="a" * 1_500_000))
    t = st.list()[0].text
    assert t == "a" * 1_000_000
    st.add(item(2, text="ب" * 700_000))
    t2 = st.list()[0].text
    assert len(t2.encode("utf-8")) <= 1_000_000 and set(t2) == {"ب"} and len(t2) == 500_000


def test_delete_unknown_noop_and_delete_clear(tmp_path):
    st = create_history_store(tmp_path / "h.db")
    st.add(item(1))
    st.delete("nope")
    assert len(st.list()) == 1
    st.delete("id1")
    assert st.list() == []
    st.add(item(1)); st.add(item(2))
    st.clear()
    assert st.list() == []


def test_persists_across_instances_and_default_path(tmp_data_dir):
    create_history_store().add(item(1))
    assert (tmp_data_dir / "history.db").is_file()
    assert [i.id for i in create_history_store().list()] == ["id1"]


def test_schema(tmp_path):
    p = tmp_path / "h.db"
    create_history_store(p).add(item(1))
    cols = [r[1] for r in sqlite3.connect(p).execute("PRAGMA table_info(history)")]
    assert cols == ["id", "source", "created", "text", "mode_used", "confidence"]
    assert sqlite3.connect(p).execute("PRAGMA journal_mode").fetchone()[0] == "delete"


def test_corrupt_db_is_renamed_and_recreated(tmp_path):
    p = tmp_path / "h.db"
    p.write_bytes(b"this is definitely not a sqlite database" * 50)
    st = create_history_store(p)
    assert st.list() == []
    assert (tmp_path / "h.db.bad").read_bytes().startswith(b"this is")
    st.add(item(1))
    assert [i.id for i in create_history_store(p).list()] == ["id1"]


def test_corruption_after_open_is_recovered(tmp_path):
    p = tmp_path / "h.db"
    st = create_history_store(p)
    st.add(item(1))
    p.write_bytes(b"garbage" * 1000)
    assert st.list() == []
    assert (tmp_path / "h.db.bad").exists()


def test_concurrent_writes(tmp_path):
    p = tmp_path / "h.db"
    st = create_history_store(p)
    errors = []

    def work(n):
        try:
            for i in range(20):
                st.add(HistoryItem(f"t{n}-{i}", "s", f"2026-01-01T00:{n:02d}:{i:02d}", "متن" * 10, "raw", 50.0))
                st.list(5)
        except Exception as e:  # pragma: no cover
            errors.append(e)

    ts = [threading.Thread(target=work, args=(n,)) for n in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errors
    assert len(st.list()) == 160
    assert sqlite3.connect(p).execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert not (tmp_path / "h.db.bad").exists()
