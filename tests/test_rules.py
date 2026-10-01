from mailvoice.core.rules import MailInfo, Rules, evaluate


def test_blocked_sender():
    """Test that a blocked sender returns blocked=True with correct reason"""
    rules = Rules(blocked_senders=("spam@domain.com",))
    mail = MailInfo(sender="spam@domain.com", subject="Test subject", body="Test body")

    result = evaluate(mail, rules)
    assert result.blocked is True
    assert result.score_bonus == 0
    assert result.reasons == ("blocked_sender",)


def test_vip_sender():
    """Test that a VIP sender gives +3 points"""
    rules = Rules(vip_senders=("boss@company.com",))
    mail = MailInfo(
        sender="boss@company.com", subject="Meeting tomorrow", body="Let's discuss the project"
    )

    result = evaluate(mail, rules)
    assert result.blocked is False
    assert result.score_bonus == 3
    assert result.reasons == ("vip_sender",)


def test_keywords():
    """Test that keywords in subject or body give points"""
    rules = Rules(keywords=("urgent", "project", "meeting"))
    mail = MailInfo(
        sender="colleague@company.com",
        subject="Urgent meeting about the project",
        body="We need to discuss the urgent project details",
    )

    result = evaluate(mail, rules)
    assert result.blocked is False
    # Should get +4 for 2 keywords (urgent and project) - max 4 points
    assert result.score_bonus == 4
    assert "keyword:urgent" in result.reasons
    assert "keyword:project" in result.reasons


def test_keywords_limit():
    """Test that only 2 keywords are counted for scoring (max +4)"""
    rules = Rules(keywords=("word1", "word2", "word3", "word4"))
    mail = MailInfo(
        sender="sender@company.com",
        subject="This message contains word1 and word2 and word3 and word4",
        body="Body with word1 and word2 and word3 and word4",
    )

    result = evaluate(mail, rules)
    assert result.blocked is False
    # Should get +4 for 2 keywords (max points) - only first 2 keywords counted
    assert result.score_bonus == 4


def test_reply_to_sent():
    """Test that reply to sent message gives +3 points"""
    rules = Rules(sent_message_ids={"msg123@company.com", "msg456@company.com"})
    mail = MailInfo(
        sender="colleague@company.com",
        subject="Re: Important update",
        body="Thanks for the update",
        in_reply_to="msg123@company.com",
    )

    result = evaluate(mail, rules)
    assert result.blocked is False
    assert result.score_bonus == 3
    assert result.reasons == ("reply_to_sent",)


def test_case_insensitive():
    """Test that all comparisons are case insensitive"""
    rules = Rules(
        vip_senders=("BOSS@COMPANY.COM",),
        keywords=("URGENT", "MEETING"),
        blocked_senders=("SPAM@DOMAIN.COM",),
    )
    mail = MailInfo(
        sender="Boss@Company.Com",
        subject="urgent meeting about project",
        body="This is an URGENT meeting",
    )

    result = evaluate(mail, rules)
    assert result.blocked is False
    assert result.score_bonus == 7  # 3 for VIP + 4 for 2 keywords
    assert "vip_sender" in result.reasons
    assert "keyword:urgent" in result.reasons
    assert "keyword:meeting" in result.reasons


def test_no_matches():
    """Test that no matches return score 0 with empty reasons"""
    rules = Rules(
        vip_senders=("boss@company.com",),
        keywords=("urgent", "meeting"),
        blocked_senders=("spam@domain.com",),
    )
    mail = MailInfo(
        sender="random@sender.com", subject="Random subject", body="Random body content"
    )

    result = evaluate(mail, rules)
    assert result.blocked is False
    assert result.score_bonus == 0
    assert result.reasons == ()


def test_references_reply():
    """Test that reply via references also works"""
    rules = Rules(sent_message_ids={"msg123@company.com", "msg456@company.com"})
    mail = MailInfo(
        sender="colleague@company.com",
        subject="Re: Important update",
        body="Thanks for the update",
        references=("msg456@company.com", "msg789@company.com"),
    )

    result = evaluate(mail, rules)
    assert result.blocked is False
    assert result.score_bonus == 3
    assert result.reasons == ("reply_to_sent",)


def test_sender_substring_matching():
    """Test that sender matching works with substrings"""
    rules = Rules(vip_senders=("@company.com",))
    mail = MailInfo(sender="boss@company.com", subject="Meeting", body="Body")

    result = evaluate(mail, rules)
    assert result.blocked is False
    assert result.score_bonus == 3
    assert result.reasons == ("vip_sender",)


def test_multiple_vip_matches_count_once():
    rules = Rules(vip_senders=("boss@", "@company.com"))
    mail = MailInfo(sender="boss@company.com", subject="s", body="b")
    result = evaluate(mail, rules)
    assert result.score_bonus == 3
    assert result.reasons == ("vip_sender",)


def test_reply_detected_via_references_when_in_reply_to_unknown():
    rules = Rules(sent_message_ids=frozenset({"<mine@x>"}))
    mail = MailInfo(
        sender="a@b.c", subject="s", body="b", in_reply_to="<other@x>", references=("<mine@x>",)
    )
    result = evaluate(mail, rules)
    assert result.score_bonus == 3
    assert result.reasons == ("reply_to_sent",)
