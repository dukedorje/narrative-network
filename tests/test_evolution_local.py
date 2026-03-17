"""Test the offline evolution subsystem."""

from evolution.local import LocalBlockClock, LocalProposalSubmitter, LocalVotingEngine


def test_local_block_clock():
    clock = LocalBlockClock(start_block=100)
    assert clock.current_block == 100
    clock.advance(50)
    assert clock.current_block == 150
    clock.advance()
    assert clock.current_block == 151


def test_full_proposal_lifecycle():
    """Full offline lifecycle: build -> submit -> register -> vote -> finalize."""
    from evolution.proposal import ProposalStatus, ProposalType
    from evolution.voting import VoteChoice

    clock = LocalBlockClock(start_block=100)
    submitter = LocalProposalSubmitter(block_clock=clock)
    engine = LocalVotingEngine(
        voter_hotkeys=["voter-0", "voter-1", "voter-2"],
        block_clock=clock,
    )

    # Build and submit proposal
    proposal = submitter.build_proposal(
        proposal_type=ProposalType.ADD_NODE,
        node_id="new-knowledge-domain",
    )
    assert proposal.status == ProposalStatus.DRAFT

    proposal = submitter.submit(proposal)
    assert proposal.status == ProposalStatus.SUBMITTED
    assert proposal.submitted_block == 100
    assert proposal.proposal_id is not None

    # Register in voting engine
    engine.register_proposal(proposal)

    # All voters vote FOR
    for hotkey in engine.voter_hotkeys:
        engine.cast_vote(proposal.proposal_id, hotkey, VoteChoice.FOR, clock.current_block)

    # Advance past voting window and finalize
    from subnet.config import VOTING_OPEN_BLOCKS
    clock.advance(VOTING_OPEN_BLOCKS + 1)

    result = engine.finalise(proposal, clock.current_block)
    assert result.passed


def test_proposal_rejection():
    """Test that a proposal with insufficient votes is rejected."""
    from evolution.proposal import ProposalType
    from evolution.voting import VoteChoice

    clock = LocalBlockClock(start_block=200)
    submitter = LocalProposalSubmitter(block_clock=clock)
    engine = LocalVotingEngine(
        voter_hotkeys=["voter-0", "voter-1", "voter-2"],
        block_clock=clock,
    )

    proposal = submitter.build_proposal(
        proposal_type=ProposalType.ADD_NODE,
        node_id="controversial-domain",
    )
    proposal = submitter.submit(proposal)
    engine.register_proposal(proposal)

    # Only one voter votes AGAINST, rest abstain
    engine.cast_vote(proposal.proposal_id, "voter-0", VoteChoice.AGAINST, clock.current_block)

    from subnet.config import VOTING_OPEN_BLOCKS
    clock.advance(VOTING_OPEN_BLOCKS + 1)

    result = engine.finalise(proposal, clock.current_block)
    assert not result.passed  # Should be rejected due to no quorum
