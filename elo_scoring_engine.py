import sqlite3
import time
from typing import Tuple, List, Optional, Dict, Any
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class ELOStats:
    candidate_id: str
    elo_score: float
    num_comparisons: int
    wins: int
    losses: int
    ties: int
    created_at: float
    updated_at: float
    
    @property
    def win_rate(self) -> float:
        return (self.wins + 0.5 * self.ties) / self.num_comparisons if self.num_comparisons else 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['win_rate'] = self.win_rate
        data['created_at'] = datetime.fromtimestamp(self.created_at).isoformat()
        data['updated_at'] = datetime.fromtimestamp(self.updated_at).isoformat()
        return data


@dataclass
class ComparisonResult:
    candidate_a: str
    candidate_b: str
    winner: str
    elo_a_before: float
    elo_b_before: float
    elo_a_after: float
    elo_b_after: float
    judge_reasoning: str
    timestamp: float
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['elo_change_a'] = self.elo_a_after - self.elo_a_before
        data['elo_change_b'] = self.elo_b_after - self.elo_b_before
        data['timestamp'] = datetime.fromtimestamp(self.timestamp).isoformat()
        return data


def calculate_elo_update(elo_a: float, elo_b: float, winner: str, k_factor: float) -> Tuple[float, float]:
    score_a = {'a': 1.0, 'tie': 0.5, 'b': 0.0}[winner]
    expected_a = 1.0 / (1.0 + 10 ** ((elo_b - elo_a) / 400.0))
    
    return (
        elo_a + k_factor * (score_a - expected_a),
        elo_b + k_factor * (1.0 - score_a - (1.0 - expected_a))
    )


class ELOScoringEngine:
    def __init__(self, db_path: str, k_factor: float = 32.0, initial_elo: float = 1500.0):
        self.db_path = Path(db_path)
        self.k_factor = k_factor
        self.initial_elo = initial_elo
        
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = self._init_db()
    
    def _init_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        self._create_schema(conn)
        return conn
    
    def _create_schema(self, conn: sqlite3.Connection):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS elo_scores (
                candidate_id TEXT PRIMARY KEY,
                elo_score REAL NOT NULL,
                num_comparisons INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                ties INTEGER DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS comparisons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_a TEXT NOT NULL,
                candidate_b TEXT NOT NULL,
                winner TEXT NOT NULL CHECK(winner IN ('a', 'b', 'tie')),
                elo_a_before REAL NOT NULL,
                elo_b_before REAL NOT NULL,
                elo_a_after REAL NOT NULL,
                elo_b_after REAL NOT NULL,
                judge_reasoning TEXT,
                timestamp REAL NOT NULL,
                UNIQUE(candidate_a, candidate_b)
            );
            
            CREATE INDEX IF NOT EXISTS idx_elo_score ON elo_scores(elo_score DESC);
            CREATE INDEX IF NOT EXISTS idx_candidate_a ON comparisons(candidate_a);
            CREATE INDEX IF NOT EXISTS idx_candidate_b ON comparisons(candidate_b);
        """)
    
    # Core functions
    def get_elo(self, candidate_id: str) -> float:
        row = self.conn.execute(
            "SELECT elo_score FROM elo_scores WHERE candidate_id = ?", 
            (candidate_id,)
        ).fetchone()
        
        if row:
            return float(row['elo_score'])
        
        now = time.time()
        self.conn.execute(
            "INSERT INTO elo_scores (candidate_id, elo_score, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (candidate_id, self.initial_elo, now, now)
        )
        self.conn.commit()
        return self.initial_elo
    
    def get_stats(self, candidate_id: str) -> Optional[ELOStats]:
        row = self.conn.execute(
            "SELECT * FROM elo_scores WHERE candidate_id = ?", 
            (candidate_id,)
        ).fetchone()
        return ELOStats(**dict(row)) if row else None
    
    def record_comparison(self, candidate_a: str, candidate_b: str, winner: str, reasoning: str = "") -> Tuple[float, float]:
        if winner not in ('a', 'b', 'tie'):
            raise ValueError(f"Invalid winner: {winner}")
        
        if self._comparison_exists(candidate_a, candidate_b):
            return self.get_elo(candidate_a), self.get_elo(candidate_b)
        
        elo_a_old, elo_b_old = self.get_elo(candidate_a), self.get_elo(candidate_b)
        elo_a_new, elo_b_new = calculate_elo_update(elo_a_old, elo_b_old, winner, self.k_factor)
        
        self._update_candidate(candidate_a, elo_a_new, winner, 'a')
        self._update_candidate(candidate_b, elo_b_new, winner, 'b')
        self._store_comparison(candidate_a, candidate_b, winner, elo_a_old, elo_b_old, elo_a_new, elo_b_new, reasoning)
        
        self.conn.commit()
        return elo_a_new, elo_b_new
    
    # Query
    def get_rankings(self, top_n: Optional[int] = None, min_comparisons: int = 0) -> List[Tuple[str, float, Dict[str, Any]]]:
        query = f"""
            SELECT candidate_id, elo_score, num_comparisons, wins, losses, ties
            FROM elo_scores WHERE num_comparisons >= ?
            ORDER BY elo_score DESC
            {f'LIMIT {top_n}' if top_n else ''}
        """
        return [
            (r['candidate_id'], r['elo_score'], {
                'comparisons': r['num_comparisons'],
                'wins': r['wins'],
                'losses': r['losses'],
                'ties': r['ties'],
                'win_rate': (r['wins'] + 0.5 * r['ties']) / max(r['num_comparisons'], 1)
            })
            for r in self.conn.execute(query, (min_comparisons,)).fetchall()
        ]
    
    def get_random_candidates(self, n: int, exclude: Optional[List[str]] = None) -> List[str]:
        if exclude:
            placeholders = ','.join('?' * len(exclude))
            query = f"SELECT candidate_id FROM elo_scores WHERE candidate_id NOT IN ({placeholders}) ORDER BY RANDOM() LIMIT ?"
            params = tuple(exclude) + (n,)
        else:
            query = "SELECT candidate_id FROM elo_scores ORDER BY RANDOM() LIMIT ?"
            params = (n,)
        
        return [r['candidate_id'] for r in self.conn.execute(query, params).fetchall()]
    
    def get_comparison_history(self, candidate_id: str) -> List[ComparisonResult]:
        return [
            ComparisonResult(**dict(row))
            for row in self.conn.execute(
                "SELECT * FROM comparisons WHERE candidate_a = ? OR candidate_b = ? ORDER BY timestamp DESC",
                (candidate_id, candidate_id)
            ).fetchall()
        ]
    
    def comparison_exists(self, candidate_a: str, candidate_b: str) -> bool:
        return self._comparison_exists(candidate_a, candidate_b)
    
    def get_comparison(self, candidate_a: str, candidate_b: str) -> Optional[ComparisonResult]:
        row = self.conn.execute(
            """SELECT * FROM comparisons 
               WHERE (candidate_a = ? AND candidate_b = ?) OR (candidate_a = ? AND candidate_b = ?)""",
            (candidate_a, candidate_b, candidate_b, candidate_a)
        ).fetchone()
        return ComparisonResult(**dict(row)) if row else None
    
    # Utility functions
    def export_data(self) -> Dict[str, Any]:
        scores = [
            ELOStats(**dict(r)).to_dict() 
            for r in self.conn.execute("SELECT * FROM elo_scores ORDER BY elo_score DESC").fetchall()
        ]
        comparisons = [
            ComparisonResult(**dict(r)).to_dict() 
            for r in self.conn.execute("SELECT * FROM comparisons ORDER BY timestamp DESC").fetchall()
        ]
        
        return {
            'metadata': {
                'k_factor': self.k_factor,
                'initial_elo': self.initial_elo,
                'total_candidates': len(scores),
                'total_comparisons': len(comparisons),
                'export_timestamp': datetime.now().isoformat(),
            },
            'scores': scores,
            'comparisons': comparisons,
        }
    
    def print_rankings(self, top_n: int = 10):
        print(f"\n{'='*70}\nELO RANKINGS (Top {top_n})\n{'='*70}")
        print(f"{'Rank':<6} {'Candidate':<25} {'ELO':<8} {'W-L-T':<12} {'WinRate':<8}\n{'-'*70}")
        
        for rank, (cid, elo, s) in enumerate(self.get_rankings(top_n), 1):
            print(f"{rank:<6} {cid:<25} {elo:<8.1f} {s['wins']}-{s['losses']}-{s['ties']:<7} {s['win_rate']:.1%}")
        
        print(f"{'='*70}\n")
    
    # Internal helpers
    def _comparison_exists(self, candidate_a: str, candidate_b: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM comparisons WHERE (candidate_a = ? AND candidate_b = ?) OR (candidate_a = ? AND candidate_b = ?)",
            (candidate_a, candidate_b, candidate_b, candidate_a)
        ).fetchone() is not None
    
    def _update_candidate(self, candidate_id: str, new_elo: float, winner: str, perspective: str):
        is_win = winner == perspective
        is_loss = winner != perspective and winner != 'tie'
        is_tie = winner == 'tie'
        
        self.conn.execute(
            """UPDATE elo_scores 
               SET elo_score = ?, num_comparisons = num_comparisons + 1,
                   wins = wins + ?, losses = losses + ?, ties = ties + ?, updated_at = ?
               WHERE candidate_id = ?""",
            (new_elo, int(is_win), int(is_loss), int(is_tie), time.time(), candidate_id)
        )
    
    def _store_comparison(self, a: str, b: str, winner: str, elo_a_old: float, elo_b_old: float, 
                         elo_a_new: float, elo_b_new: float, reasoning: str):
        self.conn.execute(
            """INSERT INTO comparisons
               (candidate_a, candidate_b, winner, elo_a_before, elo_b_before, 
                elo_a_after, elo_b_after, judge_reasoning, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (a, b, winner, elo_a_old, elo_b_old, elo_a_new, elo_b_new, reasoning, time.time())
        )
    
    # Context manager
    def close(self):
        self.conn.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
