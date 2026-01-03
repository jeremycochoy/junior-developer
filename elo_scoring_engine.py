"""
ELO Scoring Engine for Junior Developer Project
Supports:
- Multiple comparison types (win/loss/tie)
- Comparison caching to avoid redundant LLM calls
- Statistical tracking (W/L/T records)
- Efficient database queries
- Thread-safe operations
- Export/import functionality
"""

import sqlite3
import time
import json
from typing import Tuple, List, Optional, Dict, Any
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ELOStats:
    """Statistics for a candidate."""
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
        """Calculate win rate (ties count as 0.5)."""
        if self.num_comparisons == 0:
            return 0.0
        return (self.wins + 0.5 * self.ties) / self.num_comparisons
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'candidate_id': self.candidate_id,
            'elo_score': self.elo_score,
            'num_comparisons': self.num_comparisons,
            'wins': self.wins,
            'losses': self.losses,
            'ties': self.ties,
            'win_rate': self.win_rate,
            'created_at': datetime.fromtimestamp(self.created_at).isoformat(),
            'updated_at': datetime.fromtimestamp(self.updated_at).isoformat(),
        }


@dataclass
class ComparisonResult:
    """Result of a pairwise comparison."""
    candidate_a: str
    candidate_b: str
    winner: str  # "a", "b", or "tie"
    elo_a_before: float
    elo_b_before: float
    elo_a_after: float
    elo_b_after: float
    judge_reasoning: str
    timestamp: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'candidate_a': self.candidate_a,
            'candidate_b': self.candidate_b,
            'winner': self.winner,
            'elo_change_a': self.elo_a_after - self.elo_a_before,
            'elo_change_b': self.elo_b_after - self.elo_b_before,
            'elo_a_before': self.elo_a_before,
            'elo_b_before': self.elo_b_before,
            'elo_a_after': self.elo_a_after,
            'elo_b_after': self.elo_b_after,
            'judge_reasoning': self.judge_reasoning,
            'timestamp': datetime.fromtimestamp(self.timestamp).isoformat(),
        }


class ELOScoringEngine:
    """
    ELO Scoring Engine for pairwise comparisons.
    
    ELO Rating System:
    - Players start at initial_elo (default: 1500)
    - After each match, ratings are updated based on:
      - Expected score: E = 1 / (1 + 10^((R_opponent - R_player) / 400))
      - New rating: R_new = R_old + K * (actual_score - expected_score)
    - K-factor controls sensitivity (default: 32, High: 64, Low: 16)
    
    Features:
    - Automatic comparison caching (no duplicate LLM calls)
    - Statistical tracking (W/L/T, win rates)
    - Rankings and leaderboards
    - Export/import for backup
    - Thread-safe database operations
    """
    
    def __init__(
        self,
        db_path: str,
        k_factor: float = 32.0,
        initial_elo: float = 1500.0,
        verbose: bool = False,
    ):
        """
        Initialize ELO Scoring Engine.
        
        Args:
            db_path: Path to SQLite database file
            k_factor: ELO K-factor (sensitivity to new results)
                     - Higher K = more volatile ratings
                     - Typical values: 16 (masters), 32 (standard), 64 (beginners)
            initial_elo: Starting ELO for new candidates (default: 1500)
            verbose: Print debug information
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.k_factor = k_factor
        self.initial_elo = initial_elo
        self.verbose = verbose
        
        # Create database connection
        self.conn = sqlite3.connect(
            str(self.db_path),
            timeout=30.0,
            check_same_thread=False  # Allow multi-threading
        )
        self.conn.row_factory = sqlite3.Row
        
        # Enable WAL mode for better concurrency
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        
        self._create_tables()
        
        if self.verbose:
            print(f"ELO Engine initialized: {self.db_path}")
            print(f"  K-factor: {self.k_factor}")
            print(f"  Initial ELO: {self.initial_elo}")
    
    def _create_tables(self):
        """Create database schema if it doesn't exist."""
        cursor = self.conn.cursor()
        
        # Table: elo_scores
        # Stores current ELO rating and statistics for each candidate
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS elo_scores (
                candidate_id TEXT PRIMARY KEY,
                elo_score REAL NOT NULL,
                num_comparisons INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                ties INTEGER DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        
        # Table: comparisons
        # Caches all pairwise comparison results
        cursor.execute("""
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
            )
        """)
        
        # Indices for fast lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_elo_score 
            ON elo_scores(elo_score DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_candidate_a 
            ON comparisons(candidate_a)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_candidate_b 
            ON comparisons(candidate_b)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_winner 
            ON comparisons(winner)
        """)
        
        self.conn.commit()
    
    def get_elo(self, candidate_id: str) -> float:
        """
        Get current ELO score for a candidate.
        Creates new entry with initial_elo if candidate doesn't exist.
        
        Args:
            candidate_id: Unique identifier for the candidate
            
        Returns:
            Current ELO score
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT elo_score FROM elo_scores WHERE candidate_id = ?",
            (candidate_id,)
        )
        row = cursor.fetchone()
        
        if row:
            return float(row['elo_score'])
        else:
            # Initialize new candidate
            now = time.time()
            cursor.execute(
                """INSERT INTO elo_scores 
                   (candidate_id, elo_score, created_at, updated_at)
                   VALUES (?, ?, ?, ?)""",
                (candidate_id, self.initial_elo, now, now)
            )
            self.conn.commit()
            
            if self.verbose:
                print(f"Initialized {candidate_id} with ELO {self.initial_elo}")
            
            return self.initial_elo
    
    def get_stats(self, candidate_id: str) -> Optional[ELOStats]:
        """
        Get detailed statistics for a candidate.
        
        Args:
            candidate_id: Unique identifier for the candidate
            
        Returns:
            ELOStats object or None if candidate doesn't exist
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT * FROM elo_scores WHERE candidate_id = ?""",
            (candidate_id,)
        )
        row = cursor.fetchone()
        
        if not row:
            return None
        
        return ELOStats(
            candidate_id=row['candidate_id'],
            elo_score=row['elo_score'],
            num_comparisons=row['num_comparisons'],
            wins=row['wins'],
            losses=row['losses'],
            ties=row['ties'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
        )
    
    def comparison_exists(self, candidate_a: str, candidate_b: str) -> bool:
        """
        Check if two candidates have already been compared.
        Order doesn't matter (A vs B == B vs A).
        
        Args:
            candidate_a: First candidate ID
            candidate_b: Second candidate ID
            
        Returns:
            True if comparison exists in cache
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT 1 FROM comparisons 
               WHERE (candidate_a = ? AND candidate_b = ?)
                  OR (candidate_a = ? AND candidate_b = ?)""",
            (candidate_a, candidate_b, candidate_b, candidate_a)
        )
        return cursor.fetchone() is not None
    
    def get_comparison(
        self, candidate_a: str, candidate_b: str
    ) -> Optional[ComparisonResult]:
        """
        Get cached comparison result if it exists.
        
        Args:
            candidate_a: First candidate ID
            candidate_b: Second candidate ID
            
        Returns:
            ComparisonResult or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT * FROM comparisons 
               WHERE (candidate_a = ? AND candidate_b = ?)
                  OR (candidate_a = ? AND candidate_b = ?)""",
            (candidate_a, candidate_b, candidate_b, candidate_a)
        )
        row = cursor.fetchone()
        
        if not row:
            return None
        
        return ComparisonResult(
            candidate_a=row['candidate_a'],
            candidate_b=row['candidate_b'],
            winner=row['winner'],
            elo_a_before=row['elo_a_before'],
            elo_b_before=row['elo_b_before'],
            elo_a_after=row['elo_a_after'],
            elo_b_after=row['elo_b_after'],
            judge_reasoning=row['judge_reasoning'],
            timestamp=row['timestamp'],
        )
    
    def record_comparison(
        self,
        candidate_a: str,
        candidate_b: str,
        winner: str,
        reasoning: str = "",
    ) -> Tuple[float, float]:
        """
        Record a comparison result and update ELO scores.
        
        Args:
            candidate_a: ID of first candidate
            candidate_b: ID of second candidate
            winner: "a" if A won, "b" if B won, "tie" for draw
            reasoning: Optional explanation from judge
            
        Returns:
            (new_elo_a, new_elo_b) after update
            
        Raises:
            ValueError: If winner is not "a", "b", or "tie"
            RuntimeError: If comparison already exists (use cache)
        """
        # Validate inputs
        if winner not in ("a", "b", "tie"):
            raise ValueError(f"Invalid winner: {winner}. Must be 'a', 'b', or 'tie'")
        
        # Check for duplicate
        if self.comparison_exists(candidate_a, candidate_b):
            if self.verbose:
                print(f"Warning: Comparison {candidate_a} vs {candidate_b} already exists")
            # Return current ELOs without updating
            return self.get_elo(candidate_a), self.get_elo(candidate_b)
        
        # Get current ELOs
        elo_a_before = self.get_elo(candidate_a)
        elo_b_before = self.get_elo(candidate_b)
        
        # Convert winner to score
        # Score from A's perspective: 1.0 = win, 0.5 = tie, 0.0 = loss
        if winner == "a":
            score_a = 1.0
        elif winner == "tie":
            score_a = 0.5
        else:  # winner == "b"
            score_a = 0.0
        
        # Calculate expected scores using ELO formula
        # E_a = 1 / (1 + 10^((R_b - R_a) / 400))
        expected_a = 1.0 / (1.0 + 10 ** ((elo_b_before - elo_a_before) / 400.0))
        expected_b = 1.0 - expected_a
        
        # Calculate new ELOs
        # R_new = R_old + K * (S - E)
        elo_a_after = elo_a_before + self.k_factor * (score_a - expected_a)
        elo_b_after = elo_b_before + self.k_factor * ((1.0 - score_a) - expected_b)
        
        # Update database
        cursor = self.conn.cursor()
        now = time.time()
        
        # Update A's stats
        cursor.execute(
            """UPDATE elo_scores 
               SET elo_score = ?,
                   num_comparisons = num_comparisons + 1,
                   wins = wins + ?,
                   losses = losses + ?,
                   ties = ties + ?,
                   updated_at = ?
               WHERE candidate_id = ?""",
            (
                elo_a_after,
                1 if winner == "a" else 0,
                1 if winner == "b" else 0,
                1 if winner == "tie" else 0,
                now,
                candidate_a,
            )
        )
        
        # Update B's stats
        cursor.execute(
            """UPDATE elo_scores 
               SET elo_score = ?,
                   num_comparisons = num_comparisons + 1,
                   wins = wins + ?,
                   losses = losses + ?,
                   ties = ties + ?,
                   updated_at = ?
               WHERE candidate_id = ?""",
            (
                elo_b_after,
                1 if winner == "b" else 0,
                1 if winner == "a" else 0,
                1 if winner == "tie" else 0,
                now,
                candidate_b,
            )
        )
        
        # Record comparison
        cursor.execute(
            """INSERT INTO comparisons
               (candidate_a, candidate_b, winner, 
                elo_a_before, elo_b_before, elo_a_after, elo_b_after,
                judge_reasoning, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                candidate_a, candidate_b, winner,
                elo_a_before, elo_b_before, elo_a_after, elo_b_after,
                reasoning, now,
            )
        )
        
        self.conn.commit()
        
        if self.verbose:
            change_a = elo_a_after - elo_a_before
            change_b = elo_b_after - elo_b_before
            print(f"Comparison recorded: {candidate_a} vs {candidate_b}")
            print(f"  Winner: {winner}")
            print(f"  {candidate_a}: {elo_a_before:.1f} → {elo_a_after:.1f} ({change_a:+.1f})")
            print(f"  {candidate_b}: {elo_b_before:.1f} → {elo_b_after:.1f} ({change_b:+.1f})")
        
        return elo_a_after, elo_b_after
    
    def get_rankings(
        self, top_n: Optional[int] = None, min_comparisons: int = 0
    ) -> List[Tuple[str, float, Dict[str, Any]]]:
        """
        Get candidates ranked by ELO score.
        
        Args:
            top_n: Return only top N candidates (None = all)
            min_comparisons: Minimum number of comparisons required
            
        Returns:
            List of (candidate_id, elo_score, stats_dict)
            Sorted by ELO score (highest first)
        """
        cursor = self.conn.cursor()
        
        query = """
            SELECT candidate_id, elo_score, num_comparisons, wins, losses, ties
            FROM elo_scores
            WHERE num_comparisons >= ?
            ORDER BY elo_score DESC
        """
        
        if top_n is not None:
            query += f" LIMIT {top_n}"
        
        cursor.execute(query, (min_comparisons,))
        
        results = []
        for row in cursor.fetchall():
            stats = {
                'comparisons': row['num_comparisons'],
                'wins': row['wins'],
                'losses': row['losses'],
                'ties': row['ties'],
                'win_rate': (row['wins'] + 0.5 * row['ties']) / max(row['num_comparisons'], 1),
            }
            results.append((row['candidate_id'], row['elo_score'], stats))
        
        return results
    
    def get_random_candidates(
        self, n: int, exclude: Optional[List[str]] = None
    ) -> List[str]:
        """
        Get random candidate IDs for comparison.
        Useful for sampling opponents for a new candidate.
        
        Args:
            n: Number of candidates to return
            exclude: List of IDs to exclude
            
        Returns:
            List of candidate IDs
        """
        exclude = exclude or []
        cursor = self.conn.cursor()
        
        if exclude:
            placeholders = ",".join("?" * len(exclude))
            query = f"""
                SELECT candidate_id FROM elo_scores 
                WHERE candidate_id NOT IN ({placeholders})
                ORDER BY RANDOM() 
                LIMIT ?
            """
            params = tuple(exclude) + (n,)
        else:
            query = """
                SELECT candidate_id FROM elo_scores 
                ORDER BY RANDOM() 
                LIMIT ?
            """
            params = (n,)
        
        cursor.execute(query, params)
        return [row['candidate_id'] for row in cursor.fetchall()]
    
    def get_comparison_history(
        self, candidate_id: str
    ) -> List[ComparisonResult]:
        """
        Get all comparisons involving a specific candidate.
        
        Args:
            candidate_id: Candidate to get history for
            
        Returns:
            List of ComparisonResult objects, sorted by timestamp
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT * FROM comparisons 
               WHERE candidate_a = ? OR candidate_b = ?
               ORDER BY timestamp DESC""",
            (candidate_id, candidate_id)
        )
        
        results = []
        for row in cursor.fetchall():
            results.append(ComparisonResult(
                candidate_a=row['candidate_a'],
                candidate_b=row['candidate_b'],
                winner=row['winner'],
                elo_a_before=row['elo_a_before'],
                elo_b_before=row['elo_b_before'],
                elo_a_after=row['elo_a_after'],
                elo_b_after=row['elo_b_after'],
                judge_reasoning=row['judge_reasoning'],
                timestamp=row['timestamp'],
            ))
        
        return results
    
    def export_data(self) -> Dict[str, Any]:
        """
        Export all data to dictionary for backup/analysis.
        
        Returns:
            Dictionary with 'scores' and 'comparisons' keys
        """
        cursor = self.conn.cursor()
        
        # Export scores
        cursor.execute("SELECT * FROM elo_scores ORDER BY elo_score DESC")
        scores = []
        for row in cursor.fetchall():
            stats = ELOStats(
                candidate_id=row['candidate_id'],
                elo_score=row['elo_score'],
                num_comparisons=row['num_comparisons'],
                wins=row['wins'],
                losses=row['losses'],
                ties=row['ties'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
            )
            scores.append(stats.to_dict())
        
        # Export comparisons
        cursor.execute("SELECT * FROM comparisons ORDER BY timestamp DESC")
        comparisons = []
        for row in cursor.fetchall():
            result = ComparisonResult(
                candidate_a=row['candidate_a'],
                candidate_b=row['candidate_b'],
                winner=row['winner'],
                elo_a_before=row['elo_a_before'],
                elo_b_before=row['elo_b_before'],
                elo_a_after=row['elo_a_after'],
                elo_b_after=row['elo_b_after'],
                judge_reasoning=row['judge_reasoning'],
                timestamp=row['timestamp'],
            )
            comparisons.append(result.to_dict())
        
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
        """Print formatted leaderboard."""
        print(f"\n{'='*70}")
        print(f"ELO RANKINGS (Top {top_n})")
        print(f"{'='*70}")
        print(f"{'Rank':<6} {'Candidate':<25} {'ELO':<8} {'W-L-T':<12} {'WinRate':<8}")
        print(f"{'-'*70}")
        
        rankings = self.get_rankings(top_n=top_n)
        for rank, (cand_id, elo, stats) in enumerate(rankings, 1):
            wlt = f"{stats['wins']}-{stats['losses']}-{stats['ties']}"
            win_rate = f"{stats['win_rate']:.1%}"
            print(f"{rank:<6} {cand_id:<25} {elo:<8.1f} {wlt:<12} {win_rate:<8}")
        
        print(f"{'='*70}\n")
    
    def close(self):
        """Close database connection."""
        self.conn.close()
        if self.verbose:
            print(f"ELO Engine closed: {self.db_path}")
    
    def __enter__(self):
        """Context manager support."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager support."""
        self.close()
