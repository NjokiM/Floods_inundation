from django.shortcuts import render

DATA_SITES = ["nairobi", "tana"]


def index(request):
    return render(request, "sim/index.html", {"sites": DATA_SITES})
