# Unified Todo System Workflow Templates

## Agent Coordination Patterns for GitHub → Memory → TodoWrite Integration

### Template 1: GitHub Issue Initialization Pattern
```yaml
Agent Start Protocol:
  step_1_issue_review:
    action: "Review active GitHub issues with 'gh issue list --label=in-progress'"
    purpose: "Understand current project priorities and agent assignments"
    memory_tag: "issue-{number}-context"
    
  step_2_context_loading:
    action: "Read relevant PRD documents and technical specifications"
    purpose: "Load complete project context for informed task execution"
    memory_tag: "project-context-{date}"
    
  step_3_todo_creation:
    action: "Create TodoWrite list with specific, actionable tasks linked to GitHub issue"
    purpose: "Track session progress within TDD workflow phase"
    memory_tag: "session-todos-{agent}-{date}"
    
  step_4_agent_coordination:
    action: "Check for dependencies on other agents in TDD workflow"
    purpose: "Ensure proper handoffs and avoid TDD discipline violations"
    memory_tag: "tdd-handoff-{from_agent}-{to_agent}"
```

### Template 2: TDD Phase Completion Pattern
```yaml
Phase Completion Validation:
  requirements_complete:
    agent: product-design-agent
    validation: "All requirements have testable acceptance criteria"
    memory_storage: "requirements-{feature_name}: [acceptance_criteria_list]"
    handoff_trigger: "TodoWrite mark complete + Memory tag 'tdd-phase-1-complete'"
    
  tests_complete:
    agent: test-qa-agent
    validation: "All tests written and failing, coverage >80%"
    memory_storage: "failing-tests-{feature_name}: [test_list_with_status]"
    handoff_trigger: "TodoWrite mark complete + Memory tag 'tdd-phase-2-complete'"
    blocking_rule: "BLOCK any implementation without failing tests"
    
  infrastructure_complete:
    agent: infrastructure-devops-agent
    validation: "Test environments operational, infrastructure ready"
    memory_storage: "infrastructure-{environment}: [health_status_and_configs]"
    handoff_trigger: "TodoWrite mark complete + Memory tag 'tdd-phase-3-complete'"
    
  implementation_complete:
    agent: ai-ml-engineer
    validation: "All tests pass, performance targets met"
    memory_storage: "implementation-{feature_name}: [test_results_and_metrics]"
    handoff_trigger: "TodoWrite mark complete + Memory tag 'tdd-phase-4-complete'"
    
  security_complete:
    agent: security-engineer
    validation: "Security requirements met, no critical vulnerabilities"
    memory_storage: "security-validation-{feature_name}: [audit_results]"
    veto_power: "Can block deployment if security standards not met"
    final_approval: "TodoWrite mark complete + Memory tag 'tdd-phase-5-approved'"
```

### Template 3: Cross-Agent Memory Coordination
```yaml
Memory Sharing Protocol:
  shared_context_tags:
    - "project-state-{current_phase}": Overall project status accessible to all agents
    - "decisions-{component}": Architectural decisions with impact across agents
    - "blockers-{priority_level}": Issues requiring immediate cross-agent coordination
    - "performance-baselines-{metric}": System performance targets for validation
    
  agent_specific_tags:
    - "task-progress-{agent}-{issue_number}": Individual agent progress tracking
    - "handoff-context-{from}-{to}": Context transfer between TDD phases
    - "validation-results-{agent}-{criteria}": Agent-specific validation outcomes
    - "escalation-{agent}-{issue}": Problems requiring context manager intervention
    
  coordination_patterns:
    dependency_tracking: "When Agent A depends on Agent B output, tag: 'dependency-{agentA}-waiting-{agentB}'"
    collaboration_work: "When agents work together, tag: 'collaboration-{agent1}-{agent2}-{task}'"
    conflict_resolution: "When agents conflict, tag: 'conflict-{issue}-{agents}' for context manager"
```

### Template 4: Behavioral Enforcement Patterns
```yaml
Todo System Compliance:
  mandatory_usage:
    rule: "All agents MUST use TodoWrite for session coordination"
    enforcement: "Context manager monitors todo usage and intervenes if absent"
    escalation: "Agents without todos receive immediate context correction"
    
  github_integration:
    rule: "All work MUST reference active GitHub issues"
    enforcement: "TodoWrite tasks must link to specific issue numbers"
    validation: "Memory tags must include issue references"
    
  memory_consistency:
    rule: "All agents MUST follow standardized memory tagging"
    enforcement: "Context manager audits memory tags for consistency"
    correction: "Non-standard tags trigger immediate agent context update"
    
tdd_discipline_enforcement:
  test_first_rule:
    violation: "Any implementation attempt without failing tests"
    response: "IMMEDIATE BLOCKING by test-qa-agent or context manager"
    remediation: "Return to test definition phase"
    
  security_veto:
    condition: "Security engineer identifies critical issues"
    response: "IMMEDIATE DEPLOYMENT BLOCK with escalation"
    remediation: "Loop back to appropriate TDD phase for fixes"
    
  quality_gates:
    validation: "Each TDD phase completion criteria must be met"
    enforcement: "Context manager validates handoff requirements"
    blocking: "Incomplete phases block progression to next phase"
```

### Template 5: GitHub Issue Coordination Workflow
```yaml
Issue Management Protocol:
  issue_creation:
    trigger: "New feature or significant work identified"
    responsible: "Context manager coordinates with product-design-agent"
    format: "Clear title, comprehensive description, acceptance criteria"
    tags: "Appropriate labels for tracking and agent assignment"
    
  issue_breakdown:
    process: "Large issues broken into agent-specific subtasks"
    coordination: "Context manager distributes tasks across TDD workflow"
    tracking: "Each agent updates issue with progress and blockers"
    
  issue_completion:
    validation: "All acceptance criteria met and validated"
    security_approval: "Security engineer sign-off required"
    deployment_ready: "All TDD phases complete and approved"
    closure: "Issue closed with comprehensive completion summary"
    
cross_issue_dependencies:
  identification: "Context manager maps dependencies between issues"
  coordination: "Agents informed of dependencies affecting their work"
  blocking: "Dependent work blocked until prerequisites complete"
  escalation: "Dependency conflicts escalated to context manager"
```

## Implementation Guidelines

### For Agents
1. **Start Every Session**: Check GitHub issues, load project context, create TodoWrite list
2. **Memory Discipline**: Use standardized tags consistently for all stored information
3. **TDD Compliance**: Respect workflow phase requirements and handoff criteria
4. **Cross-Agent Awareness**: Check for dependencies and coordinate through memory tags

### For Context Manager
1. **Monitor Compliance**: Audit agent behavior for unified todo system adherence
2. **Enforce Standards**: Intervene when agents violate workflow or memory standards
3. **Coordinate Handoffs**: Facilitate smooth transitions between TDD phases
4. **Resolve Conflicts**: Address blocking issues and agent coordination problems

### Success Metrics
- 100% agent compliance with unified todo system
- <24 hour response time for cross-agent coordination
- Zero TDD discipline violations (no code without tests)
- >95% memory tagging consistency across agents
- >90% first-attempt success rate for complex multi-agent tasks

This framework ensures systematic task management, proper TDD discipline, and seamless multi-agent coordination while maintaining project quality and velocity.