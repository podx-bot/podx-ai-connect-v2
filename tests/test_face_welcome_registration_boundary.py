from app.services.face_welcome_policy_service import FaceWelcomePolicyService, FaceWelcomeStatus


def test_face_photo_is_not_required_for_unenrolled_universal_profile():
    service = FaceWelcomePolicyService()
    profile = service.enroll(
        user_id="universal-user",
        explicit_consent=False,
        face_template_id=None,
        display_name="Customer",
    )

    assert profile.status is FaceWelcomeStatus.NOT_ENROLLED
    assert profile.face_template_id is None
