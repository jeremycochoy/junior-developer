import sqlite3
import time
import numpy as np
from typing import Tuple, List, Optional, Dict, Any
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class BTStats:
    candidate_id: str
    bt_score: float
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
    score_a_before: float
    score_b_before: float
    score_a_after: float
    score_b_after: float
    judge_reasoning: str
    timestamp: float
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['score_change_a'] = self.score_a_after - self.score_a_before
        data['score_change_b'] = self.score_b_after - self.score_b_before
        data['timestamp'] = datetime.fromtimestamp(self.timestamp).isoformat()
        return data


def compute_bt_mm(candidates: List[str], comparisons: List[Tuple[str, str, float]], 
                  max_iter: int = 100, tol: float = 1e-6) -> Dict[str, float]:
    if not candidates:
        return {}
    
    n = len(candidates)
    idx_map = {c: i for i, c in enumerate(candidates)}
    theta = np.ones(n)
    wins = np.zeros(n)
    comp_matrix = np.zeros((n, n))
    
    for a, b, score in comparisons:
        i, j = idx_map[a], idx_map[b]
        wins[i] += score
        wins[j] += (1.0 - score)
        comp_matrix[i, j] += 1
        comp_matrix[j, i] += 1
    
    for iteration in range(max_iter):
        theta_old = theta.copy()
        for i in range(n):
            if wins[i] == 0:
                theta[i] = 1e-10
                continue
            denom = sum(comp_matrix[i, j] / (theta_old[i] + theta_old[j]) 
                       for j in range(n) if comp_matrix[i, j] > 0)
            theta[i] = wins[i] / denom if denom > 0 else 1e-10
        
        if np.max(np.abs(theta - theta_old)) < tol:
            break
    
    total = np.sum(theta)
    if total > 0:
        theta = theta / total * 1000
    
    return {candidates[i]: float(theta[i]) for i in range(n)}


class BTMMScoringEngine:
    def __init__(self, db_path: str, convergence_tol: float = 1e-6, max_iterations: int = 100):
        self.db_path = Path(db_path)
        self.convergence_tol = convergence_tol
        self.max_iterations = max_iterations
        self.initial_score = 1.0
        
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
            CREATE TABLE IF NOT EXISTS bt_scores (
                candidate_id TEXT PRIMARY KEY,
                bt_score REAL NOT NULL,
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
                score_a_before REAL NOT NULL,
                score_b_before REAL NOT NULL,
                score_a_after REAL NOT NULL,
                score_b_after REAL NOT NULL,
                judge_reasoning TEXT,
                timestamp REAL NOT NULL,
                UNIQUE(candidate_a, candidate_b)
            );
            
            CREATE INDEX IF NOT EXISTS idx_bt_score ON bt_scores(bt_score DESC);
            CREATE INDEX IF NOT EXISTS idx_candidate_a ON comparisons(candidate_a);
            CREATE INDEX IF NOT EXISTS idx_candidate_b ON comparisons(candidate_b);
        """)
    
    def get_score(self, candidate_id: str) -> float:
        row = self.conn.execute(
            "SELECT bt_score FROM bt_scores WHERE candidate_id = ?", 
            (candidate_id,)
        ).fetchone()
        
        if row:
            return float(row['bt_score'])
        
        now = time.time()
        self.conn.execute(
            "INSERT INTO bt_scores (candidate_id, bt_score, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (candidate_id, self.initial_score, now, now)
        )
        self.conn.commit()
        return self.initial_score
    
    def get_stats(self, candidate_id: str) -> Optional[BTStats]:
        row = self.conn.execute(
            "SELECT * FROM bt_scores WHERE candidate_id = ?", 
            (candidate_id,)
        ).fetchone()
        return BTStats(**dict(row)) if row else None
    
    def record_comparison(self, candidate_a: str, candidate_b: str, winner: str, reasoning: str = "") -> Tuple[float, float]:
        if winner not in ('a', 'b', 'tie'):
            raise ValueError(f"Invalid winner: {winner}")
        
        if self._comparison_exists(candidate_a, candidate_b):
            return self.get_score(candidate_a), self.get_score(candidate_b)
        
        score_a_old, score_b_old = self.get_score(candidate_a), self.get_score(candidate_b)
        
        self._update_candidate(candidate_a, winner, 'a')
        self._update_candidate(candidate_b, winner, 'b')
        
        self._store_comparison(candidate_a, candidate_b, winner, score_a_old, score_b_old, 
                            score_a_old, score_b_old, reasoning)
        
        new_scores = self._recompute_all_scores()
        score_a_new = new_scores.get(candidate_a, score_a_old)
        score_b_new = new_scores.get(candidate_b, score_b_old)
        
        self.conn.execute(
            """UPDATE comparisons 
            SET score_a_after = ?, score_b_after = ?
            WHERE candidate_a = ? AND candidate_b = ?""",
            (score_a_new, score_b_new, candidate_a, candidate_b)
        )
        
        self.conn.commit()
        return score_a_new, score_b_new
    
    def get_rankings(self, top_n: Optional[int] = None, min_comparisons: int = 0) -> List[Tuple[str, float, Dict[str, Any]]]:
        query = f"""
            SELECT candidate_id, bt_score, num_comparisons, wins, losses, ties
            FROM bt_scores WHERE num_comparisons >= ?
            ORDER BY bt_score DESC
            {f'LIMIT {top_n}' if top_n else ''}
        """
        return [
            (r['candidate_id'], r['bt_score'], {
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
            query = f"SELECT candidate_id FROM bt_scores WHERE candidate_id NOT IN ({placeholders}) ORDER BY RANDOM() LIMIT ?"
            params = tuple(exclude) + (n,)
        else:
            query = "SELECT candidate_id FROM bt_scores ORDER BY RANDOM() LIMIT ?"
            params = (n,)
        
        return [r['candidate_id'] for r in self.conn.execute(query, params).fetchall()]
    
    def get_comparison_history(self, candidate_id: str) -> List[ComparisonResult]:
        rows = self.conn.execute(
            "SELECT * FROM comparisons WHERE candidate_a = ? OR candidate_b = ? ORDER BY timestamp DESC",
            (candidate_id, candidate_id)
        ).fetchall()
        
        return [self._row_to_comparison(row) for row in rows]
    
    def comparison_exists(self, candidate_a: str, candidate_b: str) -> bool:
        return self._comparison_exists(candidate_a, candidate_b)
    
    def get_comparison(self, candidate_a: str, candidate_b: str) -> Optional[ComparisonResult]:
        row = self.conn.execute(
            """SELECT * FROM comparisons 
               WHERE (candidate_a = ? AND candidate_b = ?) OR (candidate_a = ? AND candidate_b = ?)""",
            (candidate_a, candidate_b, candidate_b, candidate_a)
        ).fetchone()
        return self._row_to_comparison(row) if row else None
    
    def export_data(self) -> Dict[str, Any]:
        scores = [
            BTStats(**dict(r)).to_dict() 
            for r in self.conn.execute("SELECT * FROM bt_scores ORDER BY bt_score DESC").fetchall()
        ]
        comparisons = [
            self._row_to_comparison(r).to_dict() 
            for r in self.conn.execute("SELECT * FROM comparisons ORDER BY timestamp DESC").fetchall()
        ]
        
        return {
            'metadata': {
                'algorithm': 'Bradley-Terry-MM',
                'convergence_tol': self.convergence_tol,
                'max_iterations': self.max_iterations,
                'total_candidates': len(scores),
                'total_comparisons': len(comparisons),
                'export_timestamp': datetime.now().isoformat(),
            },
            'scores': scores,
            'comparisons': comparisons,
        }
    
    def print_rankings(self, top_n: int = 10):
        print(f"\n{'='*70}\nBT-MM RANKINGS (Top {top_n})\n{'='*70}")
        print(f"{'Rank':<6} {'Candidate':<25} {'Score':<8} {'W-L-T':<12} {'WinRate':<8}\n{'-'*70}")
        
        for rank, (cid, score, s) in enumerate(self.get_rankings(top_n), 1):
            print(f"{rank:<6} {cid:<25} {score:<8.2f} {s['wins']}-{s['losses']}-{s['ties']:<7} {s['win_rate']:.1%}")
        
        print(f"{'='*70}\n")
    
    def _comparison_exists(self, candidate_a: str, candidate_b: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM comparisons WHERE (candidate_a = ? AND candidate_b = ?) OR (candidate_a = ? AND candidate_b = ?)",
            (candidate_a, candidate_b, candidate_b, candidate_a)
        ).fetchone() is not None
    
    def _update_candidate(self, candidate_id: str, winner: str, perspective: str):
        is_win = winner == perspective
        is_loss = winner != perspective and winner != 'tie'
        is_tie = winner == 'tie'
        
        self.conn.execute(
            """UPDATE bt_scores 
               SET num_comparisons = num_comparisons + 1,
                   wins = wins + ?, losses = losses + ?, ties = ties + ?, updated_at = ?
               WHERE candidate_id = ?""",
            (int(is_win), int(is_loss), int(is_tie), time.time(), candidate_id)
        )
    
    def _recompute_all_scores(self) -> Dict[str, float]:
        candidates = [r['candidate_id'] for r in self.conn.execute("SELECT candidate_id FROM bt_scores").fetchall()]
        comparisons = []
        for r in self.conn.execute("SELECT candidate_a, candidate_b, winner FROM comparisons").fetchall():
            score = {'a': 1.0, 'tie': 0.5, 'b': 0.0}[r['winner']]
            comparisons.append((r['candidate_a'], r['candidate_b'], score))
        
        if not comparisons:
            return {c: self.initial_score for c in candidates}
        
        new_scores = compute_bt_mm(candidates, comparisons, self.max_iterations, self.convergence_tol)
        
        for candidate_id, score in new_scores.items():
            self.conn.execute(
                "UPDATE bt_scores SET bt_score = ?, updated_at = ? WHERE candidate_id = ?",
                (score, time.time(), candidate_id)
            )
        
        return new_scores
    
    def _store_comparison(self, a: str, b: str, winner: str, score_a_old: float, score_b_old: float, 
                         score_a_new: float, score_b_new: float, reasoning: str):
        self.conn.execute(
            """INSERT INTO comparisons
               (candidate_a, candidate_b, winner, score_a_before, score_b_before, 
                score_a_after, score_b_after, judge_reasoning, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (a, b, winner, score_a_old, score_b_old, score_a_new, score_b_new, reasoning, time.time())
        )
    
    def _row_to_comparison(self, row) -> ComparisonResult:
        return ComparisonResult(
            candidate_a=row['candidate_a'],
            candidate_b=row['candidate_b'],
            winner=row['winner'],
            score_a_before=row['score_a_before'],
            score_b_before=row['score_b_before'],
            score_a_after=row['score_a_after'],
            score_b_after=row['score_b_after'],
            judge_reasoning=row['judge_reasoning'],
            timestamp=row['timestamp']
        )
    
    def close(self):
        self.conn.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
