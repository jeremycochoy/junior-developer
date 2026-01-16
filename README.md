# Junior Developer 🧬

> Self-evolving coding agent using genetic algorithms and Bradley-Terry pairwise comparison

A sophisticated system that uses **ShinkaEvolve** (genetic programming framework) combined with **Bradley-Terry with Minorization-Maximization (BT-MM)** scoring to evolve effective coding agent prompts through pairwise LLM-based evaluation.

## 🎯 What Does It Do?

Instead of manually crafting prompts for coding agents, this system:

1. **Starts** with seed prompts (e.g., "Refactor visualization code")
2. **Evolves** prompts through genetic algorithms (mutation via LLM)
3. **Evaluates** results by comparing pairs of branches using an LLM judge
4. **Ranks** all attempts using BT-MM scoring (statistically optimal)
5. **Converges** on high-quality, specific refactoring instructions

## 🏗️ Architecture

```
┌─────────────────┐
│  ShinkaEvolve   │  Genetic algorithm orchestration
│   (AlphaEvolve) │  Population management, mutation
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  evaluate.py    │  Evaluation pipeline
│                 │  • Execute coding agent
│                 │  • Create Git branches
│                 │  • Generate diffs
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Pairwise Judge  │  LLM compares two branches
│   (judge.py)    │  • Randomized ordering
│                 │  • Returns winner + reasoning
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  BT-MM Scoring  │  Ranking algorithm
│  (scoring.py)   │  • Global optimization
│                 │  • No hyperparameters
└─────────────────┘
```

## ✨ Key Features

### **Bradley-Terry with MM (Not ELO)**
- ✅ **Globally optimal**: Maximum Likelihood Estimation
- ✅ **No tuning**: No K-factor or learning rate
- ✅ **Efficient**: O(N × iterations) not O(N²)
- ✅ **Batch updates**: Recomputes all scores together
- ✅ **Statistically principled**: Proper probabilistic model

### **Pairwise Comparison**
- ✅ **LLM-as-Judge**: Single LLM compares two candidates
- ✅ **Unbiased**: Randomized ordering (A/B positions)
- ✅ **Context-aware**: Includes task spec and diffs
- ✅ **Reasoning tracked**: Stores judge's explanation

### **Git-Based Population**
- ✅ **Branch per candidate**: Easy versioning
- ✅ **Diff comparison**: Natural code comparison
- ✅ **Rollback**: Clean state management

## 📦 Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/junior-developer.git
cd junior-developer

# Install in development mode
pip install -e .

# Or install with all dependencies
pip install -e ".[dev,llm]"
```

## 🚀 Quick Start

### 1. Run Tests

```bash
# Run all tests
pytest tests/

# Run specific test suite
pytest tests/test_scoring.py -v
pytest tests/test_judge.py -v
```

### 2. Basic Usage

```python
from junior_dev import BTMMScoringEngine, PairwiseJudge

# Initialize BT-MM scoring engine
engine = BTMMScoringEngine(
    db_path="scores.db",
    initial_score=1.0,
    convergence_tol=1e-6
)

# Initialize judge
judge = PairwiseJudge(llm_model="gpt-4")

# Compare two candidates
result = judge.compare(
    candidate_a_id="branch_001",
    candidate_a_output="Refactored code A",
    candidate_b_id="branch_002",
    candidate_b_output="Refactored code B",
    task_spec="Move visualization to separate class",
    context=""
)

# Record comparison
score_a, score_b = engine.record_comparison(
    candidate_a="branch_001",
    candidate_b="branch_002",
    winner=result.winner,
    reasoning=result.reasoning
)

print(f"Scores: {score_a:.4f} vs {score_b:.4f}")

# Get rankings
rankings = engine.get_rankings()
for rank, stats in enumerate(rankings, 1):
    print(f"{rank}. {stats.candidate_id}: {stats.bt_score:.4f}")
```

### 3. Integration with ShinkaEvolve

```bash
# Run evolution
cd examples/
python -m shinka.runner --config config.yaml
```

## 📁 Project Structure

```
junior-developer/
├── junior_dev/              # Main package
│   ├── __init__.py
│   ├── scoring.py           # BT-MM scoring engine
│   ├── judge.py             # Pairwise LLM judge
│   └── shinka/              # ShinkaEvolve integration
│       ├── __init__.py
│       ├── evaluate.py      # Evaluation pipeline
│       └── initial.py       # Seed prompts
├── tests/                   # Test suite
│   ├── test_scoring.py      # BT-MM tests (11 tests)
│   ├── test_judge.py        # Judge tests (10 tests)
│   └── test_evaluate.py     # Integration test
├── archive/                 # Reference implementations
│   ├── elo_scoring_engine.py
│   └── simple_demo.py
├── docs/                    # Documentation
├── examples/                # Usage examples
├── configs/                 # Configuration files
├── requirements.txt         # Dependencies
├── setup.py                 # Package setup
└── README.md
```

## 🔬 How BT-MM Works

### The Math (Simplified)

**Bradley-Terry Model**: Probability that A beats B is:

```
P(A beats B) = score_A / (score_A + score_B)
```

**Minorization-Maximization**: Iteratively update scores until convergence:

```python
for iteration in range(max_iterations):
    for candidate_i in candidates:
        wins_i = sum(comparisons where i won)
        games_i = sum(all comparisons involving i)
        
        denominator = sum(
            1 / (score_i + score_j) 
            for each opponent j
        )
        
        new_score_i = wins_i / denominator
    
    if converged:
        break
```

**Result**: Globally optimal scores that maximize likelihood of observed outcomes.

## 🧪 Testing

All tests are comprehensive and passing:

```bash
# BT-MM Scoring Engine (11 tests)
pytest tests/test_scoring.py -v

# Pairwise Judge (10 tests)  
pytest tests/test_judge.py -v

# Integration (1 test)
pytest tests/test_evaluate.py -v
```

## 📊 Performance

- **Convergence**: Typically 10-20 iterations
- **Complexity**: O(N × C × I) where:
  - N = number of candidates
  - C = comparisons per candidate (~10)
  - I = iterations (~15)
- **Scalability**: Tested with 100+ candidates
- **Cost**: ~$0.50 per 50 generations (with GPT-4)

## 🛠️ Configuration

See `configs/` directory for examples:

- `task/`: Task specifications
- `evolution/`: Population and generation settings
- `database/`: Archive configuration
- `agent/`: Coding agent settings


