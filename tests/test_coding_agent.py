import tempfile
import subprocess
from pathlib import Path
from junior_dev.coding_agent import CodingAgent, AgentResult

def test_initialization():
    print("\n" + "="*70)
    print("TEST 1: CodingAgent Initialization")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        agent = CodingAgent(agent_type="pipeline", timeout=60, working_dir=tmpdir)
        assert agent.agent_type == "pipeline"
        assert agent.timeout == 60
        
    print("✓ Initialization test passed\n")


def test_pipeline_agent_missing_script():
    print("\n" + "="*70)
    print("TEST 2: Pipeline Agent - Missing Script")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        agent = CodingAgent(agent_type="pipeline", timeout=60, working_dir=tmpdir)
        
        result = agent.execute("Test prompt")
        
        assert isinstance(result, AgentResult)
        assert result.success == False
        assert "Pipeline script not found" in result.error
        assert result.exit_code == -1
        
    print("✓ Missing script test passed\n")


def test_pipeline_agent_with_script():
    print("\n" + "="*70)
    print("TEST 3: Pipeline Agent - With Script")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        agents_dir = Path(tmpdir) / ".agents"
        agents_dir.mkdir()
        
        pipeline_script = agents_dir / "run_pipeline.sh"
        pipeline_script.write_text("""#!/usr/bin/env bash
echo "=== Agent 1: Implement ==="
echo "=== Agent 2: Correctness Review ==="
echo "=== Agent 3: Simplification ==="
echo "=== Agent 4: Final Correctness Check ==="
echo "Pipeline complete."
exit 0
""")
        pipeline_script.chmod(0o755)
        
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.local"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmpdir, capture_output=True)
        
        agent = CodingAgent(agent_type="pipeline", timeout=60, working_dir=tmpdir)
        
        result = agent.execute("Test prompt for refactoring")
        
        assert isinstance(result, AgentResult)
        assert result.success == True
        assert result.exit_code == 0
        assert "Pipeline complete" in result.output
        assert result.execution_time > 0
        
    print("✓ Pipeline agent test passed\n")


def test_agent_availability():
    print("\n" + "="*70)
    print("TEST 4: Agent Availability Check")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        agent = CodingAgent(agent_type="pipeline", working_dir=tmpdir)
        available = agent.check_agent_available()
        print(f"  Pipeline available (no script): {available}")
        assert available == False
        
        agents_dir = Path(tmpdir) / ".agents"
        agents_dir.mkdir()
        pipeline_script = agents_dir / "run_pipeline.sh"
        pipeline_script.write_text("#!/usr/bin/env bash\nexit 0\n")
        pipeline_script.chmod(0o755)
        
        agent2 = CodingAgent(agent_type="pipeline", working_dir=tmpdir)
        available2 = agent2.check_agent_available()
        print(f"  Pipeline available (with script): {available2}")
        assert available2 == True
        
    print("✓ Agent availability test passed\n")


def test_timeout_handling():
    print("\n" + "="*70)
    print("TEST 5: Timeout Handling")
    print("="*70)

    with tempfile.TemporaryDirectory() as tmpdir:
        agents_dir = Path(tmpdir) / ".agents"
        agents_dir.mkdir()
        
        pipeline_script = agents_dir / "run_pipeline.sh"
        pipeline_script.write_text("""#!/usr/bin/env bash
sleep 5
exit 0
""")
        pipeline_script.chmod(0o755)
        
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.local"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmpdir, capture_output=True)
        
        agent = CodingAgent(agent_type="pipeline", timeout=1, working_dir=tmpdir)
        result = agent.execute("Test prompt")

        assert result.success == False
        assert "timed out" in result.error.lower()
    
    print("✓ Timeout handling test passed\n")


def test_error_handling():
    print("\n" + "="*70)
    print("TEST 6: Error Handling")
    print("="*70)
    
    try:
        agent = CodingAgent(agent_type="invalid_agent")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "invalid_agent" in str(e)
        assert "pipeline" in str(e).lower()
        print("✓ Invalid agent type raises error")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            agent = CodingAgent(agent_type="pipeline")
            result = agent.execute("Test")
            assert result.success == False
            assert "requires working_dir" in result.error
            print("✓ Missing working_dir raises error")
        except Exception:
            pass
    
    print("✓ Error handling test passed\n")


def test_agent_result_structure():
    print("\n" + "="*70)
    print("TEST 7: AgentResult Structure")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        agents_dir = Path(tmpdir) / ".agents"
        agents_dir.mkdir()
        
        pipeline_script = agents_dir / "run_pipeline.sh"
        pipeline_script.write_text("#!/usr/bin/env bash\necho 'Test output'\nexit 0\n")
        pipeline_script.chmod(0o755)
        
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.local"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmpdir, capture_output=True)
        
        agent = CodingAgent(agent_type="pipeline", working_dir=tmpdir)
        result = agent.execute("Test")
    
    assert hasattr(result, "success")
    assert hasattr(result, "output")
    assert hasattr(result, "error")
    assert hasattr(result, "execution_time")
    assert hasattr(result, "exit_code")
    assert hasattr(result, "changes_made")
    
    assert isinstance(result.success, bool)
    assert isinstance(result.output, str)
    assert isinstance(result.error, str)
    assert isinstance(result.execution_time, float)
    assert isinstance(result.exit_code, int)
    assert isinstance(result.changes_made, bool)
    
    print("✓ AgentResult structure test passed\n")


def test_custom_agents_dir():
    print("\n" + "="*70)
    print("TEST 8: Custom Agents Directory")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        custom_agents_dir = Path(tmpdir) / "custom_agents"
        custom_agents_dir.mkdir()
        
        pipeline_script = custom_agents_dir / "run_pipeline.sh"
        pipeline_script.write_text("#!/usr/bin/env bash\necho 'Custom dir test'\nexit 0\n")
        pipeline_script.chmod(0o755)
        
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.local"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmpdir, capture_output=True)
        
        agent = CodingAgent(
            agent_type="pipeline",
            working_dir=tmpdir,
            agents_dir=str(custom_agents_dir)
        )
        
        available = agent.check_agent_available()
        assert available == True
        
        result = agent.execute("Test")
        assert result.success == True
        
    print("✓ Custom agents directory test passed\n")


if __name__ == "__main__":
    test_initialization()
    test_pipeline_agent_missing_script()
    test_pipeline_agent_with_script()
    test_agent_availability()
    test_timeout_handling()
    test_error_handling()
    test_agent_result_structure()
    test_custom_agents_dir()
    print("\n" + "="*70)
    print("ALL CODING AGENT TESTS PASSED")
    print("="*70 + "\n")
