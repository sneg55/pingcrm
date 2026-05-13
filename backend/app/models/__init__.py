from app.models.contact import Contact
from app.models.contact_merge import ContactMerge
from app.models.detected_event import DetectedEvent
from app.models.extension_pairing import ExtensionPairing
from app.models.follow_up import FollowUpSuggestion
from app.models.google_account import GoogleAccount
from app.models.identity_match import IdentityMatch
from app.models.interaction import Interaction
from app.models.org_identity_match import OrgIdentityMatch
from app.models.notification import Notification
from app.models.organization import Organization
from app.models.tag_taxonomy import TagTaxonomy
from app.models.user import User

# Register SQLAlchemy event listeners (must import to execute @event.listens_for)
from app.models import listeners  # noqa: F401,E402

__all__ = [
    "User",
    "Contact",
    "ContactMerge",
    "ExtensionPairing",
    "Interaction",
    "DetectedEvent",
    "FollowUpSuggestion",
    "GoogleAccount",
    "IdentityMatch",
    "Notification",
    "OrgIdentityMatch",
    "Organization",
    "TagTaxonomy",
]
