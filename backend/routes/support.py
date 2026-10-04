from fastapi import APIRouter, Depends

import auth
from models import Counsellor, UserOut

router = APIRouter(tags=["support"])

# Demo directory. Not real people — placeholder data for the prototype.
_COUNSELLORS = [
    Counsellor(
        name="Dr. Ananya Rao",
        title="Clinical Psychologist",
        languages=["English", "Hindi", "Kannada"],
        phone="+91 98765 43210",
        email="ananya.rao@example.com",
        available="Mon–Fri, 9am–6pm",
    ),
    Counsellor(
        name="Karthik Menon",
        title="Counselling Therapist",
        languages=["English", "Tamil", "Malayalam"],
        phone="+91 91234 56780",
        email="karthik.menon@example.com",
        available="Mon–Sat, 11am–8pm",
    ),
    Counsellor(
        name="Dr. Sara Fernandes",
        title="Psychiatrist",
        languages=["English", "Hindi", "Konkani"],
        phone="+91 99887 66554",
        email="sara.fernandes@example.com",
        available="Tue–Sun, 10am–5pm",
    ),
    Counsellor(
        name="Ravi Deshmukh",
        title="Student Wellness Counsellor",
        languages=["English", "Hindi", "Marathi"],
        phone="+91 90000 12345",
        email="ravi.deshmukh@example.com",
        available="Mon–Fri, 8am–4pm",
    ),
]


@router.get("/counsellors", response_model=list[Counsellor])
async def get_counsellors(_user: UserOut = Depends(auth.get_current_user)) -> list[Counsellor]:
    """Return the (demo) list of counsellors a user can talk to."""
    return _COUNSELLORS
