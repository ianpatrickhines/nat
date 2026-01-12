"""
NationBuilder V2 API Tools

All tools for interacting with the NationBuilder V2 API, organized by resource type.
Each tool is decorated with @tool for use with the Claude Agent SDK.
"""

import json
from typing import Any

from claude_agent_sdk import tool

from .client import get_client


def _text_response(text: str) -> dict[str, Any]:
    """Helper to create a text response."""
    return {"content": [{"type": "text", "text": text}]}


def _json_response(data: Any) -> dict[str, Any]:
    """Helper to create a JSON response."""
    return {"content": [{"type": "text", "text": json.dumps(data, indent=2)}]}


def _error_response(error: str) -> dict[str, Any]:
    """Helper to create an error response."""
    return {"content": [{"type": "text", "text": f"Error: {error}"}], "is_error": True}


# =============================================================================
# SIGNUPS (People)
# =============================================================================

@tool(
    "list_signups",
    "List people/signups with optional filtering and pagination. Use to search your nation's database by email, name, phone, volunteer status, donor status, etc.",
    {
        "filter": dict,
        "page_size": int,
        "page_number": int,
        "include": list,
        "sort": str
    }
)
async def list_signups(args: dict[str, Any]) -> dict[str, Any]:
    """List signups with optional filters."""
    try:
        client = get_client()
        result = await client.list(
            "signups",
            filter=args.get("filter"),
            page_size=args.get("page_size", 20),
            page_number=args.get("page_number", 1),
            include=args.get("include"),
            sort=args.get("sort")
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "get_signup",
    "Get a single person by ID with full details. Optionally sideload related data like donations, contacts, tags, memberships, and path journeys.",
    {
        "id": str,
        "include": list
    }
)
async def get_signup(args: dict[str, Any]) -> dict[str, Any]:
    """Get a single signup by ID."""
    try:
        client = get_client()
        result = await client.get(
            "signups",
            args["id"],
            include=args.get("include")
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "create_signup",
    "Create a new person in the nation. Requires at least one of: email, first_name, last_name, or phone_number.",
    {
        "email": str,
        "first_name": str,
        "last_name": str,
        "phone_number": str,
        "mobile_number": str,
        "employer": str,
        "occupation": str,
        "is_volunteer": bool,
        "email_opt_in": bool,
        "mobile_opt_in": bool,
        "do_not_contact": bool,
        "do_not_call": bool,
        "note": str,
        "recruiter_id": str,
        "external_id": str
    }
)
async def create_signup(args: dict[str, Any]) -> dict[str, Any]:
    """Create a new signup."""
    try:
        client = get_client()
        result = await client.create("signups", args)
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "update_signup",
    "Update an existing person's information.",
    {
        "id": str,
        "email": str,
        "first_name": str,
        "last_name": str,
        "phone_number": str,
        "mobile_number": str,
        "employer": str,
        "occupation": str,
        "is_volunteer": bool,
        "email_opt_in": bool,
        "mobile_opt_in": bool,
        "do_not_contact": bool,
        "do_not_call": bool,
        "note": str
    }
)
async def update_signup(args: dict[str, Any]) -> dict[str, Any]:
    """Update an existing signup."""
    try:
        client = get_client()
        signup_id = args.pop("id")
        result = await client.update("signups", signup_id, args)
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "delete_signup",
    "Delete a person from the nation. Use with caution - this is irreversible.",
    {"id": str}
)
async def delete_signup(args: dict[str, Any]) -> dict[str, Any]:
    """Delete a signup."""
    try:
        client = get_client()
        await client.delete("signups", args["id"])
        return _text_response(f"Successfully deleted signup {args['id']}")
    except Exception as e:
        return _error_response(str(e))


# =============================================================================
# SIGNUP TAGS
# =============================================================================

@tool(
    "list_signup_tags",
    "List all tags available in the nation.",
    {
        "page_size": int,
        "page_number": int
    }
)
async def list_signup_tags(args: dict[str, Any]) -> dict[str, Any]:
    """List all signup tags."""
    try:
        client = get_client()
        result = await client.list(
            "signup_tags",
            page_size=args.get("page_size", 20),
            page_number=args.get("page_number", 1)
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "create_signup_tag",
    "Create a new tag in the nation.",
    {"name": str}
)
async def create_signup_tag(args: dict[str, Any]) -> dict[str, Any]:
    """Create a new signup tag."""
    try:
        client = get_client()
        result = await client.create("signup_tags", {"name": args["name"]})
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "tag_signup",
    "Add a tag to a person by creating a signup_tagging.",
    {
        "signup_id": str,
        "signup_tag_id": str
    }
)
async def tag_signup(args: dict[str, Any]) -> dict[str, Any]:
    """Tag a signup."""
    try:
        client = get_client()
        result = await client.create("signup_taggings", {
            "signup_id": args["signup_id"],
            "signup_tag_id": args["signup_tag_id"]
        })
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "untag_signup",
    "Remove a tag from a person by deleting the signup_tagging.",
    {"tagging_id": str}
)
async def untag_signup(args: dict[str, Any]) -> dict[str, Any]:
    """Remove a tag from a signup."""
    try:
        client = get_client()
        await client.delete("signup_taggings", args["tagging_id"])
        return _text_response(f"Successfully removed tagging {args['tagging_id']}")
    except Exception as e:
        return _error_response(str(e))


@tool(
    "list_signup_taggings",
    "List tag assignments with optional filtering by signup_id or signup_tag_id.",
    {
        "filter": dict,
        "page_size": int,
        "page_number": int,
        "include": list
    }
)
async def list_signup_taggings(args: dict[str, Any]) -> dict[str, Any]:
    """List signup taggings."""
    try:
        client = get_client()
        result = await client.list(
            "signup_taggings",
            filter=args.get("filter"),
            page_size=args.get("page_size", 20),
            page_number=args.get("page_number", 1),
            include=args.get("include")
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


# =============================================================================
# CONTACTS (Interaction Logs)
# =============================================================================

@tool(
    "log_contact",
    "Log a contact/interaction with a person. Records phone calls, emails, door knocks, meetings, etc.",
    {
        "signup_id": str,
        "author_id": str,
        "contact_method": str,
        "contact_status": str,
        "content": str,
        "path_id": str,
        "path_step_id": str,
        "broadcaster_id": str
    }
)
async def log_contact(args: dict[str, Any]) -> dict[str, Any]:
    """Create a contact log entry."""
    try:
        client = get_client()
        result = await client.create("contacts", args)
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "list_contacts",
    "List contact history with optional filtering by signup_id, author_id, contact_method, etc.",
    {
        "filter": dict,
        "page_size": int,
        "page_number": int,
        "include": list
    }
)
async def list_contacts(args: dict[str, Any]) -> dict[str, Any]:
    """List contacts."""
    try:
        client = get_client()
        result = await client.list(
            "contacts",
            filter=args.get("filter"),
            page_size=args.get("page_size", 20),
            page_number=args.get("page_number", 1),
            include=args.get("include")
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "get_contact",
    "Get details of a specific contact log entry.",
    {
        "id": str,
        "include": list
    }
)
async def get_contact(args: dict[str, Any]) -> dict[str, Any]:
    """Get a single contact."""
    try:
        client = get_client()
        result = await client.get(
            "contacts",
            args["id"],
            include=args.get("include")
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "update_contact",
    "Update an existing contact log entry.",
    {
        "id": str,
        "contact_status": str,
        "content": str
    }
)
async def update_contact(args: dict[str, Any]) -> dict[str, Any]:
    """Update a contact."""
    try:
        client = get_client()
        contact_id = args.pop("id")
        result = await client.update("contacts", contact_id, args)
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "delete_contact",
    "Delete a contact log entry.",
    {"id": str}
)
async def delete_contact(args: dict[str, Any]) -> dict[str, Any]:
    """Delete a contact."""
    try:
        client = get_client()
        await client.delete("contacts", args["id"])
        return _text_response(f"Successfully deleted contact {args['id']}")
    except Exception as e:
        return _error_response(str(e))


# =============================================================================
# DONATIONS
# =============================================================================

@tool(
    "list_donations",
    "List donations with optional filtering by signup_id, amount, date, etc.",
    {
        "filter": dict,
        "page_size": int,
        "page_number": int,
        "include": list,
        "sort": str
    }
)
async def list_donations(args: dict[str, Any]) -> dict[str, Any]:
    """List donations."""
    try:
        client = get_client()
        result = await client.list(
            "donations",
            filter=args.get("filter"),
            page_size=args.get("page_size", 20),
            page_number=args.get("page_number", 1),
            include=args.get("include"),
            sort=args.get("sort")
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "get_donation",
    "Get details of a specific donation.",
    {
        "id": str,
        "include": list
    }
)
async def get_donation(args: dict[str, Any]) -> dict[str, Any]:
    """Get a single donation."""
    try:
        client = get_client()
        result = await client.get(
            "donations",
            args["id"],
            include=args.get("include")
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "create_donation",
    "Record a donation for a person. Amount is in cents (e.g., 10000 = $100).",
    {
        "signup_id": str,
        "amount_in_cents": int,
        "payment_type_name": str,
        "succeeded_at": str,
        "donation_tracking_code_id": str,
        "employer": str,
        "occupation": str,
        "check_number": str,
        "note": str
    }
)
async def create_donation(args: dict[str, Any]) -> dict[str, Any]:
    """Create a donation."""
    try:
        client = get_client()
        result = await client.create("donations", args)
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "update_donation",
    "Update an existing donation record.",
    {
        "id": str,
        "note": str,
        "employer": str,
        "occupation": str
    }
)
async def update_donation(args: dict[str, Any]) -> dict[str, Any]:
    """Update a donation."""
    try:
        client = get_client()
        donation_id = args.pop("id")
        result = await client.update("donations", donation_id, args)
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "delete_donation",
    "Delete a donation record.",
    {"id": str}
)
async def delete_donation(args: dict[str, Any]) -> dict[str, Any]:
    """Delete a donation."""
    try:
        client = get_client()
        await client.delete("donations", args["id"])
        return _text_response(f"Successfully deleted donation {args['id']}")
    except Exception as e:
        return _error_response(str(e))


# =============================================================================
# EVENTS
# =============================================================================

@tool(
    "list_events",
    "List events in the nation.",
    {
        "filter": dict,
        "page_size": int,
        "page_number": int,
        "include": list,
        "sort": str
    }
)
async def list_events(args: dict[str, Any]) -> dict[str, Any]:
    """List events."""
    try:
        client = get_client()
        result = await client.list(
            "events",
            filter=args.get("filter"),
            page_size=args.get("page_size", 20),
            page_number=args.get("page_number", 1),
            include=args.get("include"),
            sort=args.get("sort")
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "get_event",
    "Get details of a specific event.",
    {
        "id": str,
        "include": list
    }
)
async def get_event(args: dict[str, Any]) -> dict[str, Any]:
    """Get a single event."""
    try:
        client = get_client()
        result = await client.get(
            "events",
            args["id"],
            include=args.get("include")
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "create_event",
    "Create a new event.",
    {
        "name": str,
        "status": str,
        "start_time": str,
        "end_time": str,
        "venue_name": str,
        "venue_address": str,
        "capacity": int,
        "contact_email": str,
        "intro": str
    }
)
async def create_event(args: dict[str, Any]) -> dict[str, Any]:
    """Create an event."""
    try:
        client = get_client()
        result = await client.create("events", args)
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "update_event",
    "Update an existing event.",
    {
        "id": str,
        "name": str,
        "status": str,
        "start_time": str,
        "end_time": str,
        "venue_name": str,
        "capacity": int
    }
)
async def update_event(args: dict[str, Any]) -> dict[str, Any]:
    """Update an event."""
    try:
        client = get_client()
        event_id = args.pop("id")
        result = await client.update("events", event_id, args)
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "delete_event",
    "Delete an event.",
    {"id": str}
)
async def delete_event(args: dict[str, Any]) -> dict[str, Any]:
    """Delete an event."""
    try:
        client = get_client()
        await client.delete("events", args["id"])
        return _text_response(f"Successfully deleted event {args['id']}")
    except Exception as e:
        return _error_response(str(e))


# =============================================================================
# EVENT RSVPs
# =============================================================================

@tool(
    "list_event_rsvps",
    "List RSVPs for events with optional filtering.",
    {
        "filter": dict,
        "page_size": int,
        "page_number": int,
        "include": list
    }
)
async def list_event_rsvps(args: dict[str, Any]) -> dict[str, Any]:
    """List event RSVPs."""
    try:
        client = get_client()
        result = await client.list(
            "event_rsvps",
            filter=args.get("filter"),
            page_size=args.get("page_size", 20),
            page_number=args.get("page_number", 1),
            include=args.get("include")
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "create_event_rsvp",
    "RSVP a person to an event.",
    {
        "event_id": str,
        "signup_id": str,
        "guests_count": int,
        "canceled": bool
    }
)
async def create_event_rsvp(args: dict[str, Any]) -> dict[str, Any]:
    """Create an event RSVP."""
    try:
        client = get_client()
        result = await client.create("event_rsvps", args)
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "update_event_rsvp",
    "Update an existing RSVP.",
    {
        "id": str,
        "guests_count": int,
        "canceled": bool,
        "attended": bool
    }
)
async def update_event_rsvp(args: dict[str, Any]) -> dict[str, Any]:
    """Update an event RSVP."""
    try:
        client = get_client()
        rsvp_id = args.pop("id")
        result = await client.update("event_rsvps", rsvp_id, args)
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "delete_event_rsvp",
    "Delete an RSVP.",
    {"id": str}
)
async def delete_event_rsvp(args: dict[str, Any]) -> dict[str, Any]:
    """Delete an event RSVP."""
    try:
        client = get_client()
        await client.delete("event_rsvps", args["id"])
        return _text_response(f"Successfully deleted RSVP {args['id']}")
    except Exception as e:
        return _error_response(str(e))


# =============================================================================
# PATHS & PATH JOURNEYS
# =============================================================================

@tool(
    "list_paths",
    "List all paths (workflows) in the nation.",
    {
        "page_size": int,
        "page_number": int,
        "include": list
    }
)
async def list_paths(args: dict[str, Any]) -> dict[str, Any]:
    """List paths."""
    try:
        client = get_client()
        result = await client.list(
            "paths",
            page_size=args.get("page_size", 20),
            page_number=args.get("page_number", 1),
            include=args.get("include")
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "get_path",
    "Get a path with its steps.",
    {
        "id": str,
        "include": list
    }
)
async def get_path(args: dict[str, Any]) -> dict[str, Any]:
    """Get a single path."""
    try:
        client = get_client()
        result = await client.get(
            "paths",
            args["id"],
            include=args.get("include", ["path_steps"])
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "list_path_journeys",
    "List path journeys (people in paths) with optional filtering.",
    {
        "filter": dict,
        "page_size": int,
        "page_number": int,
        "include": list
    }
)
async def list_path_journeys(args: dict[str, Any]) -> dict[str, Any]:
    """List path journeys."""
    try:
        client = get_client()
        result = await client.list(
            "path_journeys",
            filter=args.get("filter"),
            page_size=args.get("page_size", 20),
            page_number=args.get("page_number", 1),
            include=args.get("include")
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "assign_to_path",
    "Assign a person to a path (create path_journey).",
    {
        "signup_id": str,
        "path_id": str,
        "point_person_id": str
    }
)
async def assign_to_path(args: dict[str, Any]) -> dict[str, Any]:
    """Assign a signup to a path."""
    try:
        client = get_client()
        result = await client.create("path_journeys", args)
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "update_path_journey",
    "Update a person's path journey (change step, point person, etc.).",
    {
        "id": str,
        "path_step_id": str,
        "point_person_id": str
    }
)
async def update_path_journey(args: dict[str, Any]) -> dict[str, Any]:
    """Update a path journey."""
    try:
        client = get_client()
        journey_id = args.pop("id")
        result = await client.update("path_journeys", journey_id, args)
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "delete_path_journey",
    "Remove a person from a path.",
    {"id": str}
)
async def delete_path_journey(args: dict[str, Any]) -> dict[str, Any]:
    """Delete a path journey."""
    try:
        client = get_client()
        await client.delete("path_journeys", args["id"])
        return _text_response(f"Successfully removed path journey {args['id']}")
    except Exception as e:
        return _error_response(str(e))


# =============================================================================
# AUTOMATIONS
# =============================================================================

@tool(
    "list_automations",
    "List all automations in the nation.",
    {
        "filter": dict,
        "page_size": int,
        "page_number": int
    }
)
async def list_automations(args: dict[str, Any]) -> dict[str, Any]:
    """List automations."""
    try:
        client = get_client()
        result = await client.list(
            "automations",
            filter=args.get("filter"),
            page_size=args.get("page_size", 20),
            page_number=args.get("page_number", 1)
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "get_automation",
    "Get details of a specific automation.",
    {"id": str}
)
async def get_automation(args: dict[str, Any]) -> dict[str, Any]:
    """Get a single automation."""
    try:
        client = get_client()
        result = await client.get("automations", args["id"])
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "enroll_in_automation",
    "Enroll a person in an automation.",
    {
        "signup_id": str,
        "automation_id": str,
        "campaign_source": str,
        "campaign_url": str
    }
)
async def enroll_in_automation(args: dict[str, Any]) -> dict[str, Any]:
    """Enroll a signup in an automation."""
    try:
        client = get_client()
        result = await client.create("automation_enrollments", args)
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "list_automation_enrollments",
    "List automation enrollments with optional filtering.",
    {
        "filter": dict,
        "page_size": int,
        "page_number": int,
        "include": list
    }
)
async def list_automation_enrollments(args: dict[str, Any]) -> dict[str, Any]:
    """List automation enrollments."""
    try:
        client = get_client()
        result = await client.list(
            "automation_enrollments",
            filter=args.get("filter"),
            page_size=args.get("page_size", 20),
            page_number=args.get("page_number", 1),
            include=args.get("include")
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


# =============================================================================
# LISTS
# =============================================================================

@tool(
    "list_lists",
    "List all saved lists in the nation.",
    {
        "page_size": int,
        "page_number": int
    }
)
async def list_lists(args: dict[str, Any]) -> dict[str, Any]:
    """List saved lists."""
    try:
        client = get_client()
        result = await client.list(
            "lists",
            page_size=args.get("page_size", 20),
            page_number=args.get("page_number", 1)
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "get_list",
    "Get details of a specific list.",
    {"id": str}
)
async def get_list(args: dict[str, Any]) -> dict[str, Any]:
    """Get a single list."""
    try:
        client = get_client()
        result = await client.get("lists", args["id"])
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "get_list_members",
    "Get people in a saved list.",
    {
        "list_id": str,
        "page_size": int,
        "page_number": int
    }
)
async def get_list_members(args: dict[str, Any]) -> dict[str, Any]:
    """Get members of a list."""
    try:
        client = get_client()
        result = await client.list_related(
            "lists",
            args["list_id"],
            "signups",
            page_size=args.get("page_size", 20),
            page_number=args.get("page_number", 1)
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "add_to_list",
    "Add a person to a list.",
    {
        "list_id": str,
        "signup_id": str
    }
)
async def add_to_list(args: dict[str, Any]) -> dict[str, Any]:
    """Add a signup to a list."""
    try:
        client = get_client()
        result = await client.add_related(
            "lists",
            args["list_id"],
            "signups",
            [args["signup_id"]]
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "remove_from_list",
    "Remove a person from a list.",
    {
        "list_id": str,
        "signup_id": str
    }
)
async def remove_from_list(args: dict[str, Any]) -> dict[str, Any]:
    """Remove a signup from a list."""
    try:
        client = get_client()
        await client.remove_related(
            "lists",
            args["list_id"],
            "signups",
            [args["signup_id"]]
        )
        return _text_response(f"Successfully removed signup from list")
    except Exception as e:
        return _error_response(str(e))


# =============================================================================
# SURVEYS
# =============================================================================

@tool(
    "list_surveys",
    "List all surveys in the nation.",
    {
        "page_size": int,
        "page_number": int,
        "include": list
    }
)
async def list_surveys(args: dict[str, Any]) -> dict[str, Any]:
    """List surveys."""
    try:
        client = get_client()
        result = await client.list(
            "surveys",
            page_size=args.get("page_size", 20),
            page_number=args.get("page_number", 1),
            include=args.get("include")
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "get_survey",
    "Get survey details with questions and possible responses.",
    {
        "id": str,
        "include": list
    }
)
async def get_survey(args: dict[str, Any]) -> dict[str, Any]:
    """Get a single survey."""
    try:
        client = get_client()
        result = await client.get(
            "surveys",
            args["id"],
            include=args.get("include", ["survey_questions"])
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "record_survey_response",
    "Record a person's response to a survey question.",
    {
        "signup_id": str,
        "survey_question_id": str,
        "response": str
    }
)
async def record_survey_response(args: dict[str, Any]) -> dict[str, Any]:
    """Record a survey response."""
    try:
        client = get_client()
        result = await client.create("survey_question_responses", args)
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


# =============================================================================
# PETITIONS
# =============================================================================

@tool(
    "list_petitions",
    "List all petitions.",
    {
        "page_size": int,
        "page_number": int
    }
)
async def list_petitions(args: dict[str, Any]) -> dict[str, Any]:
    """List petitions."""
    try:
        client = get_client()
        result = await client.list(
            "petitions",
            page_size=args.get("page_size", 20),
            page_number=args.get("page_number", 1)
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "get_petition",
    "Get details of a specific petition.",
    {"id": str}
)
async def get_petition(args: dict[str, Any]) -> dict[str, Any]:
    """Get a single petition."""
    try:
        client = get_client()
        result = await client.get("petitions", args["id"])
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "sign_petition",
    "Add a signature to a petition.",
    {
        "petition_id": str,
        "signup_id": str
    }
)
async def sign_petition(args: dict[str, Any]) -> dict[str, Any]:
    """Sign a petition."""
    try:
        client = get_client()
        result = await client.create("petition_signatures", args)
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "list_petition_signatures",
    "List signatures for a petition.",
    {
        "filter": dict,
        "page_size": int,
        "page_number": int
    }
)
async def list_petition_signatures(args: dict[str, Any]) -> dict[str, Any]:
    """List petition signatures."""
    try:
        client = get_client()
        result = await client.list(
            "petition_signatures",
            filter=args.get("filter"),
            page_size=args.get("page_size", 20),
            page_number=args.get("page_number", 1)
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


# =============================================================================
# MEMBERSHIPS
# =============================================================================

@tool(
    "list_memberships",
    "List memberships with optional filtering.",
    {
        "filter": dict,
        "page_size": int,
        "page_number": int,
        "include": list
    }
)
async def list_memberships(args: dict[str, Any]) -> dict[str, Any]:
    """List memberships."""
    try:
        client = get_client()
        result = await client.list(
            "memberships",
            filter=args.get("filter"),
            page_size=args.get("page_size", 20),
            page_number=args.get("page_number", 1),
            include=args.get("include")
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "create_membership",
    "Create a membership for a person.",
    {
        "signup_id": str,
        "membership_type_id": str,
        "started_at": str,
        "expires_at": str
    }
)
async def create_membership(args: dict[str, Any]) -> dict[str, Any]:
    """Create a membership."""
    try:
        client = get_client()
        result = await client.create("memberships", args)
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "list_membership_types",
    "List available membership types.",
    {
        "page_size": int,
        "page_number": int
    }
)
async def list_membership_types(args: dict[str, Any]) -> dict[str, Any]:
    """List membership types."""
    try:
        client = get_client()
        result = await client.list(
            "membership_types",
            page_size=args.get("page_size", 20),
            page_number=args.get("page_number", 1)
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


# =============================================================================
# MAILINGS
# =============================================================================

@tool(
    "list_mailings",
    "List email blasts/mailings.",
    {
        "filter": dict,
        "page_size": int,
        "page_number": int
    }
)
async def list_mailings(args: dict[str, Any]) -> dict[str, Any]:
    """List mailings."""
    try:
        client = get_client()
        result = await client.list(
            "mailings",
            filter=args.get("filter"),
            page_size=args.get("page_size", 20),
            page_number=args.get("page_number", 1)
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "get_mailing",
    "Get details of a specific mailing.",
    {"id": str}
)
async def get_mailing(args: dict[str, Any]) -> dict[str, Any]:
    """Get a single mailing."""
    try:
        client = get_client()
        result = await client.get("mailings", args["id"])
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


# =============================================================================
# CUSTOM FIELDS
# =============================================================================

@tool(
    "list_custom_fields",
    "List all custom fields defined in the nation.",
    {
        "page_size": int,
        "page_number": int
    }
)
async def list_custom_fields(args: dict[str, Any]) -> dict[str, Any]:
    """List custom fields."""
    try:
        client = get_client()
        result = await client.list(
            "custom_fields",
            page_size=args.get("page_size", 20),
            page_number=args.get("page_number", 1)
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


# =============================================================================
# PLEDGES
# =============================================================================

@tool(
    "list_pledges",
    "List pledges with optional filtering.",
    {
        "filter": dict,
        "page_size": int,
        "page_number": int,
        "include": list
    }
)
async def list_pledges(args: dict[str, Any]) -> dict[str, Any]:
    """List pledges."""
    try:
        client = get_client()
        result = await client.list(
            "pledges",
            filter=args.get("filter"),
            page_size=args.get("page_size", 20),
            page_number=args.get("page_number", 1),
            include=args.get("include")
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "create_pledge",
    "Create a pledge for a person.",
    {
        "signup_id": str,
        "amount_in_cents": int,
        "pledged_at": str
    }
)
async def create_pledge(args: dict[str, Any]) -> dict[str, Any]:
    """Create a pledge."""
    try:
        client = get_client()
        result = await client.create("pledges", args)
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


# =============================================================================
# BROADCASTERS
# =============================================================================

@tool(
    "list_broadcasters",
    "List all broadcasters (email/text senders) in the nation.",
    {
        "page_size": int,
        "page_number": int
    }
)
async def list_broadcasters(args: dict[str, Any]) -> dict[str, Any]:
    """List broadcasters."""
    try:
        client = get_client()
        result = await client.list(
            "broadcasters",
            page_size=args.get("page_size", 20),
            page_number=args.get("page_number", 1)
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "get_broadcaster",
    "Get details of a specific broadcaster.",
    {"id": str}
)
async def get_broadcaster(args: dict[str, Any]) -> dict[str, Any]:
    """Get a single broadcaster."""
    try:
        client = get_client()
        result = await client.get("broadcasters", args["id"])
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


# =============================================================================
# ELECTIONS & VOTERS
# =============================================================================

@tool(
    "list_elections",
    "List elections.",
    {
        "page_size": int,
        "page_number": int
    }
)
async def list_elections(args: dict[str, Any]) -> dict[str, Any]:
    """List elections."""
    try:
        client = get_client()
        result = await client.list(
            "elections",
            page_size=args.get("page_size", 20),
            page_number=args.get("page_number", 1)
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "list_voters",
    "List voter records.",
    {
        "filter": dict,
        "page_size": int,
        "page_number": int,
        "include": list
    }
)
async def list_voters(args: dict[str, Any]) -> dict[str, Any]:
    """List voters."""
    try:
        client = get_client()
        result = await client.list(
            "voters",
            filter=args.get("filter"),
            page_size=args.get("page_size", 20),
            page_number=args.get("page_number", 1),
            include=args.get("include")
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


# =============================================================================
# PAGES
# =============================================================================

@tool(
    "list_pages",
    "List pages in the nation.",
    {
        "filter": dict,
        "page_size": int,
        "page_number": int
    }
)
async def list_pages(args: dict[str, Any]) -> dict[str, Any]:
    """List pages."""
    try:
        client = get_client()
        result = await client.list(
            "pages",
            filter=args.get("filter"),
            page_size=args.get("page_size", 20),
            page_number=args.get("page_number", 1)
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "get_page",
    "Get details of a specific page.",
    {"id": str}
)
async def get_page(args: dict[str, Any]) -> dict[str, Any]:
    """Get a single page."""
    try:
        client = get_client()
        result = await client.get("pages", args["id"])
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


# =============================================================================
# DONATION TRACKING CODES
# =============================================================================

@tool(
    "list_donation_tracking_codes",
    "List donation tracking codes for campaign attribution.",
    {
        "page_size": int,
        "page_number": int
    }
)
async def list_donation_tracking_codes(args: dict[str, Any]) -> dict[str, Any]:
    """List donation tracking codes."""
    try:
        client = get_client()
        result = await client.list(
            "donation_tracking_codes",
            page_size=args.get("page_size", 20),
            page_number=args.get("page_number", 1)
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


# =============================================================================
# ALL TOOLS LIST
# =============================================================================

ALL_TOOLS = [
    # Signups
    list_signups,
    get_signup,
    create_signup,
    update_signup,
    delete_signup,
    # Tags
    list_signup_tags,
    create_signup_tag,
    tag_signup,
    untag_signup,
    list_signup_taggings,
    # Contacts
    log_contact,
    list_contacts,
    get_contact,
    update_contact,
    delete_contact,
    # Donations
    list_donations,
    get_donation,
    create_donation,
    update_donation,
    delete_donation,
    # Events
    list_events,
    get_event,
    create_event,
    update_event,
    delete_event,
    # Event RSVPs
    list_event_rsvps,
    create_event_rsvp,
    update_event_rsvp,
    delete_event_rsvp,
    # Paths
    list_paths,
    get_path,
    list_path_journeys,
    assign_to_path,
    update_path_journey,
    delete_path_journey,
    # Automations
    list_automations,
    get_automation,
    enroll_in_automation,
    list_automation_enrollments,
    # Lists
    list_lists,
    get_list,
    get_list_members,
    add_to_list,
    remove_from_list,
    # Surveys
    list_surveys,
    get_survey,
    record_survey_response,
    # Petitions
    list_petitions,
    get_petition,
    sign_petition,
    list_petition_signatures,
    # Memberships
    list_memberships,
    create_membership,
    list_membership_types,
    # Mailings
    list_mailings,
    get_mailing,
    # Custom Fields
    list_custom_fields,
    # Pledges
    list_pledges,
    create_pledge,
    # Broadcasters
    list_broadcasters,
    get_broadcaster,
    # Elections & Voters
    list_elections,
    list_voters,
    # Pages
    list_pages,
    get_page,
    # Donation Tracking
    list_donation_tracking_codes,
]
