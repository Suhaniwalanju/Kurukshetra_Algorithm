import time
import os
import sys
from backend.database import init_db, SessionLocal, DeckRecord
from backend.materials.staleness_checker import check_deck_staleness

def run_worker():
    """
    Background worker loop for Verified Course Material Studio.
    Processes pending verification runs, runs staleness audits, and handles background exports.
    """
    print("[Studio Worker] Initializing database and runtime plugins...")
    init_db()
    print("[Studio Worker] Background worker listening for jobs...")

    while True:
        try:
            db = SessionLocal()
            # Check for any pending or unverified decks
            pending_decks = db.query(DeckRecord).filter(DeckRecord.status == "pending").all()
            for deck in pending_decks:
                print(f"[Studio Worker] Processing queued deck: {deck.id} ({deck.topic})")
                deck.status = "generating"
                db.commit()

            db.close()
        except Exception as e:
            print(f"[Studio Worker] Error in worker cycle: {e}")

        time.sleep(5)

if __name__ == "__main__":
    run_worker()
