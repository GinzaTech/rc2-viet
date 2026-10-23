"""User-selected Gmail labels for three exact RC2 sign-in hints.

This is display wording only. Account validation and generic email support stay
unchanged. Gmail is not a general translation or synonym of ``email``.
"""

SOURCE_SHA256 = "9bec52ed4c43aad6c615b0a7a0650f0d35e842c4bf8a5e59d5da005a50d56b6a"
REVISION = "r14.6.1-12116-full-review-gmail-1"

ENGLISH = {
    "account_guide_input_box_hint_subtitle": "Enter phone number or email",
    "account_guide_subtitle": "Enter Phone Number or Email",
    "account_email_transfer_register_input_hint_title": "Enter email",
}

TRANSLATIONS = {
    "account_guide_input_box_hint_subtitle": "Nhập số điện thoại hay Gmail",
    "account_guide_subtitle": "Nhập số điện thoại hay Gmail",
    "account_email_transfer_register_input_hint_title": "Nhập Gmail",
}

# These pairs are comparison-only and require both the exact key and source.
# They must never be added to the general product-spelling equivalent list.
TOKEN_EQUIVALENTS = {
    "account_guide_input_box_hint_subtitle": ("email", "Gmail"),
    "account_guide_subtitle": ("Email", "Gmail"),
    "account_email_transfer_register_input_hint_title": ("email", "Gmail"),
}


def approved_equivalent(name, original, pair):
    """Approve only the explicitly requested exact-source account hint pair."""
    return (name in ENGLISH and original == ENGLISH[name]
            and tuple(pair) == TOKEN_EQUIVALENTS[name])
