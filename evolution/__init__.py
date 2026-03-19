"""Evolution package for Bittensor Knowledge Network subnet.

Provides on-chain governance mechanisms:
- proposal: NodeProposal creation, submission, and bond management
- voting: VotingEngine for cast/tally/finalise lifecycle
- pruning: PruningEngine for score-based node lifecycle management
- integration: IntegrationManager for ramp-in of accepted proposals
"""

from evolution.integration import IntegrationManager, IntegrationState, ForeshadowingNotice
from evolution.proposal import (
    ProposalStatus,
    ProposalType,
    NodeProposal,
    ProposalSubmitter,
)
from evolution.pruning import PrunePhase, PruneState, PruningEngine
from evolution.voting import VoteChoice, Vote, TallyResult, VotingEngine

__all__ = [
    "ProposalStatus",
    "ProposalType",
    "NodeProposal",
    "ProposalSubmitter",
    "VoteChoice",
    "Vote",
    "TallyResult",
    "VotingEngine",
    "PrunePhase",
    "PruneState",
    "PruningEngine",
    "IntegrationState",
    "ForeshadowingNotice",
    "IntegrationManager",
]
