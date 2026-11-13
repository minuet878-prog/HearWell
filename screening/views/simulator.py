from django.shortcuts import render
from django.templatetags.static import static

from screening.simulator import FREQUENCIES, LEVELS, LIMITS, NORMAL_LINE, SENTENCES


def hearing_loss_simulator(request):
    # #487 (spec #484): open without logging in, like 了解 and the family zone it is listed on; it
    # reads no records, so it is not a 健康資料頁面.
    data = {
        "frequencies": FREQUENCIES,
        "levels": LEVELS,
        "normal": NORMAL_LINE,
        "sentences": [
            {"text": text, "voice": voice, "audio": static(f"screening/simulator/sentence-{n}.m4a")}
            for n, (text, voice) in enumerate(SENTENCES, start=1)
        ],
        "limits": LIMITS,
    }
    return render(
        request,
        "screening/simulator.html",
        {"data": data, "sentences": SENTENCES, "limits": LIMITS},
    )
