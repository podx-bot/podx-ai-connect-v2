from app.services.face_welcome_policy_service import (
    FaceWelcomePolicyService,
    FaceWelcomeStatus,
)


def test_face_welcome_cannot_enroll_without_explicit_consent():
    service = FaceWelcomePolicyService()
    profile = service.enroll(
        user_id="u1",
        explicit_consent=False,
        face_template_id="template-1",
        display_name="Manohar",
    )

    assert profile.status is FaceWelcomeStatus.NOT_ENROLLED
    assert profile.consent_active is False
    assert profile.face_template_id is None


def test_face_welcome_enrollment_requires_template_after_consent():
    service = FaceWelcomePolicyService()

    try:
        service.enroll(
            user_id="u1",
            explicit_consent=True,
            face_template_id=None,
        )
    except ValueError as exc:
        assert "face_template_id" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_matching_only_triggers_after_enrollment_consent_and_match():
    service = FaceWelcomePolicyService()
    profile = service.enroll(
        user_id="u1",
        explicit_consent=True,
        face_template_id="template-1",
        display_name="Manohar",
    )

    no_match = service.evaluate_match(profile=profile, biometric_match=False)
    assert no_match.allow_match is False
    assert no_match.greeting is None

    matched = service.evaluate_match(profile=profile, biometric_match=True)
    assert matched.allow_match is True
    assert matched.greeting == "Welcome Manohar!"


def test_disabling_face_welcome_revokes_match_and_removes_template_reference():
    service = FaceWelcomePolicyService()
    enrolled = service.enroll(
        user_id="u1",
        explicit_consent=True,
        face_template_id="template-1",
        display_name="Manohar",
    )
    disabled = service.disable(enrolled)

    assert disabled.status is FaceWelcomeStatus.DISABLED
    assert disabled.consent_active is False
    assert disabled.face_template_id is None

    decision = service.evaluate_match(profile=disabled, biometric_match=True)
    assert decision.allow_match is False
    assert decision.greeting is None
