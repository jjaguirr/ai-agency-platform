# Behavioral Enforcement Configuration

## Unified Todo System Behavioral Patterns

### Agent Behavior Requirements

#### Universal Requirements (All Agents)
```yaml
mandatory_behaviors:
  session_initialization:
    - MUST check active GitHub issues before starting any work
    - MUST create TodoWrite list for session coordination  
    - MUST load relevant project context from PRD documents
    - MUST tag all memory entries with standardized conventions
    
  cross_agent_coordination:
    - MUST check for TDD phase dependencies before starting work
    - MUST update GitHub issues with progress and blockers
    - MUST store completed work in memory with proper task-progress tags
    - MUST coordinate handoffs through memory tags and TodoWrite completion
    
  quality_assurance:
    - MUST validate completion criteria before marking tasks complete
    - MUST reference GitHub issues in all work-related activities
    - MUST follow TDD workflow phase requirements strictly
    - MUST escalate blockers to context manager when appropriate
```

#### Agent-Specific Behavioral Rules

##### Product-Design-Agent
```yaml
requirements_definition_behavior:
  - MUST convert all business requirements into testable acceptance criteria
  - MUST create comprehensive UI/UX specifications with measurable criteria  
  - MUST validate requirements completeness before handoff to test-qa-agent
  - MUST store requirements in memory with "requirements-{feature_name}" tags
  - MUST mark TodoWrite complete only when all requirements have acceptance criteria
```

##### Test-QA-Agent  
```yaml
test_first_enforcement:
  - MUST write failing tests for ALL requirements before any implementation
  - MUST achieve >80% test coverage for all critical functionality
  - MUST BLOCK any implementation attempts without failing tests
  - MUST coordinate with infrastructure-devops-agent on test environment needs
  - MUST store failing test status in memory with "failing-tests-{feature_name}" tags
  - VETO POWER: Can block any code progression until test discipline maintained
```

##### Infrastructure-DevOps-Agent
```yaml
environment_readiness_behavior:
  - MUST ensure test environments operational before implementation handoff
  - MUST validate performance baselines (<500ms memory recall SLA)
  - MUST verify customer isolation mechanisms in infrastructure
  - MUST coordinate with test-qa-agent on test environment specifications
  - MUST store infrastructure status in memory with "infrastructure-{environment}" tags
```

##### AI-ML-Engineer
```yaml
implementation_discipline:
  - BLOCKED from implementation until failing tests exist from test-qa-agent
  - MUST pass ALL existing tests before marking implementation complete
  - MUST validate performance requirements (<500ms memory recall)
  - MUST verify customer isolation in all implementation work
  - MUST store implementation results in memory with "implementation-{feature_name}" tags
```

##### Security-Engineer
```yaml
security_validation_authority:
  - VETO POWER: Can block deployment if critical security issues found
  - MUST validate 100% customer memory isolation
  - MUST audit all security patterns and access controls
  - MUST verify compliance with enterprise security requirements
  - MUST store security validation in memory with "security-validation-{feature_name}" tags
  - FINAL APPROVAL: Required before any production deployment
```

##### Subagent-Context-Manager
```yaml
orchestration_responsibilities:
  - MUST monitor all agent behavior for unified todo system compliance
  - MUST enforce TDD discipline violations immediately
  - MUST coordinate cross-agent handoffs and memory sharing
  - MUST maintain master knowledge graph of project state
  - MUST resolve conflicts and escalate blockers appropriately
```

### Violation Detection & Response

#### TDD Discipline Violations
```yaml
implementation_without_tests:
  detection: "AI-ML-Engineer attempts code implementation without failing tests"
  response: "IMMEDIATE BLOCKING by test-qa-agent or context manager"
  message: "TDD violation detected. Implementation blocked until failing tests exist."
  remediation: "Return to test definition phase (Phase 2)"
  
security_standards_violation:
  detection: "Security engineer identifies critical security issues"
  response: "IMMEDIATE DEPLOYMENT BLOCK with veto authority"
  message: "Critical security issues found. Deployment blocked pending remediation."
  remediation: "Loop back to appropriate phase for fixes"
  
incomplete_phase_handoff:
  detection: "Agent attempts handoff without meeting completion criteria"
  response: "Context manager blocks handoff and provides corrective guidance"
  message: "Phase handoff blocked. Completion criteria not met."
  remediation: "Complete phase requirements before handoff"
```

#### Todo System Violations
```yaml
missing_todowrite:
  detection: "Agent working without TodoWrite session coordination"
  response: "Context manager intervention with immediate TodoWrite creation"
  message: "Todo system compliance violation. Session coordination required."
  remediation: "Create TodoWrite list with current session tasks"
  
github_issue_non_reference:
  detection: "Agent work not linked to active GitHub issues"
  response: "Context manager redirects work to reference appropriate issues"
  message: "GitHub issue integration required. Work must reference active issues."
  remediation: "Link current work to relevant GitHub issue"
  
memory_tagging_inconsistency:
  detection: "Agent using non-standard memory tags"
  response: "Context manager provides immediate tagging correction"
  message: "Memory tagging standards violated. Use standardized conventions."
  remediation: "Update memory tags to follow standard format"
```

### Enforcement Escalation Protocol

#### Level 1: Immediate Correction
- Agent behavior monitoring detects minor violations
- Context manager provides immediate guidance and correction
- Agent implements correction and continues work
- Violation logged for pattern analysis

#### Level 2: Session Intervention
- Repeated violations or significant discipline breaches
- Context manager takes direct control of agent session
- Complete context refresh and behavioral reinforcement
- Agent configuration update if necessary

#### Level 3: Agent Configuration Update
- Persistent violations indicating configuration problems
- Context manager updates agent .md file with enhanced behavioral rules
- Complete agent re-initialization with new behavioral patterns
- Extended monitoring period to validate compliance

#### Level 4: Workflow Escalation
- System-wide compliance issues affecting project delivery
- Context manager escalates to technical lead for process review
- Potential agent workflow restructuring or additional constraints
- Comprehensive system audit and optimization

### Performance Metrics & Monitoring

#### Compliance Tracking
```yaml
behavioral_metrics:
  todo_system_usage: "Percentage of agent sessions using TodoWrite (target: 100%)"
  github_integration: "Percentage of work linked to GitHub issues (target: 100%)"
  memory_tag_consistency: "Percentage of memory tags following standards (target: >95%)"
  tdd_discipline: "Percentage of implementation following test-first (target: 100%)"
  
coordination_metrics:
  handoff_success_rate: "Percentage of clean TDD phase handoffs (target: >90%)"
  agent_response_time: "Time to respond to cross-agent coordination (target: <24h)"
  blocker_resolution_time: "Time to resolve escalated issues (target: <4h)"
  quality_gate_compliance: "Percentage of phases meeting completion criteria (target: 100%)"
  
project_velocity_metrics:
  feature_completion_rate: "Features completed per sprint with quality compliance"
  rework_reduction: "Percentage decrease in rework due to TDD discipline"
  customer_isolation_violations: "Number of customer isolation breaches (target: 0)"
  performance_sla_compliance: "Percentage meeting <500ms memory recall (target: 100%)"
```

### Implementation Timeline

#### Week 1: Initial Deployment
- Deploy behavioral enforcement across all 6 agents
- Monitor compliance and collect baseline metrics
- Address immediate violations with Level 1 corrections
- Document patterns and optimize enforcement rules

#### Week 2: Performance Optimization
- Analyze agent compliance patterns and bottlenecks
- Implement Level 2 interventions for persistent violations
- Optimize memory tagging standards based on usage patterns
- Enhance cross-agent coordination workflows

#### Week 3: System Maturation
- Deploy Level 3 agent configuration updates as needed
- Achieve >95% compliance across all behavioral requirements
- Validate project velocity improvements from systematic coordination
- Document best practices and success patterns

#### Week 4: Continuous Improvement
- Establish ongoing monitoring and optimization processes
- Create automated compliance checking and reporting
- Train agents on advanced coordination patterns
- Prepare for scale-up to additional project contexts

This behavioral enforcement configuration ensures systematic adherence to unified todo system requirements while maintaining high productivity and quality standards across all agent interactions.