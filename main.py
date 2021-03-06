import os
import sys
import random
from typing import Type, Dict
from tqdm.contrib.concurrent import process_map
from tqdm import tqdm

from dependency_injector.wiring import Provide, inject

from core.implements import (
    Station,
    Transmitter,
    Medium,
    Frame,
    FrameRadius,
    FrameStorage,
    FramePath,
    FrameRadiusEdge,
    CSMA,
)
from core.time.line import TimeLine
from core.container import DIContainer
from config import default_settings, various_settings
from utils.log import (
    log_result,
    logger_factory,
    station_notate,
    frame_notate,
    summary_settings,
)


@inject
def simulate(
    settings: Dict = Provide[DIContainer.config.settings],
    timeline: TimeLine = Provide[DIContainer.timeline],
    medium: Type[Medium] = Provide[DIContainer.medium],
):
    medium = medium(
        star_topology=settings["star_topology"],
        propagation_speed=settings["propagation_speed"],
        station_count=settings["station_count"],
        area_size=settings["area_size"],
    )
    medium.init_stations(
        data_rate=settings["data_rate"],
        frame_rate=settings["frame_rate"],
        detect_range=settings["detect_range"],
        slot_time=settings["slot_time"],
        with_rts=settings["with_rts"],
    )
    if settings["log"]:
        timeline.set_after_tick(logger_factory(settings))
    timeline.run()
    return timeline


def wire(settings: Dict = default_settings):
    di_container = DIContainer()
    di_container.config.from_dict(
        {
            "settings": {
                **settings,
            },
            "notation": [
                {"instance": Station, "notation": station_notate},
                {"instance": Frame, "notation": frame_notate},
                {"instance": FramePath, "notation": "* "},
                {"instance": FrameRadiusEdge, "notation": "+ "},
                {"instance": FrameRadius, "notation": "- "},
                {"instance": "default", "notation": "  "},
            ],
            "medium": Medium,
            "station": Station,
            "frame": Frame,
            "frame_storage": FrameStorage,
            "transmitter": Transmitter,
            "csma": CSMA,
        }
    )
    di_container.wire(modules=[__name__])


def simulate_and_save_result(settings: Dict = default_settings):
    wire(settings)
    timeline = simulate()
    log_result(timeline, settings)


if __name__ == "__main__":
    simulation = False
    pass_done = False
    multiprocess = False

    if "--simulation" in sys.argv:
        simulation = True
    if "--pass-done" in sys.argv:
        pass_done = True
    if "--multiprocess" in sys.argv:
        multiprocess = True

    if not simulation:
        wire(default_settings)
        timeline = simulate()
        exit()

    settings = (
        various_settings
        if not pass_done
        else [
            settings
            for settings in various_settings
            if f"{summary_settings(settings)}.csv" not in os.listdir("results/csv")
        ]
    )

    random.shuffle(settings)

    i = 0
    while True:
        i += len(settings)
        if multiprocess:
            process_map(simulate_and_save_result, settings, max_workers=4)
        else:
            for s in tqdm(settings):
                simulate_and_save_result(s)
        print(i)
