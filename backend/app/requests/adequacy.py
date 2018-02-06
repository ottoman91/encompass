"""
Handle requests to the adequacy endpoint.

The /api/adequacy/ enpoint accepts a list of providers and a list of service areas
or representative points.

REQUEST - POST  /api/adequacies/

{
  providers: [{id, lat, long}]
  service_area_ids: [str]
}

RESPONSE
[
  {
    id: 17323,
    closest_provider_by_distance: int,
    closest_provider_by_time: int,
    time_to_clostest_provider: int,
    distance_to_closest_povider: float
  }
]
"""
import json
import logging
import os
import random

from backend.app.exceptions.format import InvalidFormat
from backend.app.mocks.responses import mock_adequacy
from backend.config import config
from backend.lib.calculate import adequacy
from backend.lib.fetch import representative_points

from retrying import retry

WAIT_FIXED_MILLISECONDS = 500
STOP_MAX_ATTEMPT_NUMBER = 2
DATASET_CACHE_DIRECTORY = config.get('cached_result_directory')

logger = logging.getLogger(__name__)


def mock_adequacy_calculation(provider_ids, service_area_ids):
    """Mock adequacy calculation."""
    points = representative_points.fetch_representative_points(service_area_ids)
    point_ids = [point['id'] for point in points]

    return [
        mock_adequacy(point_id, random.choice(provider_ids))
        for point_id in point_ids
    ]


@retry(
    wait_fixed=WAIT_FIXED_MILLISECONDS,
    stop_max_attempt_number=STOP_MAX_ATTEMPT_NUMBER)
def adequacy_request(app, flask_request, engine):
    """Handle /api/adequacy/ requests."""
    logger.info('Calculating adequacies.')
    try:
        request = flask_request.get_json(force=True)
    except json.JSONDecodeError:
        raise InvalidFormat(message='Invalid JSON format.')

    if 'providers' not in request:
        raise InvalidFormat(message='Invalid format. Could not find provider information.')
    if 'service_area_ids' not in request:
        raise InvalidFormat(message='Invalid format. Could not find service_area_ids.')
    if 'method' not in request:
        raise InvalidFormat(message='Invalid format. Could not find method.')

    provider_locations = request['providers']
    service_area_ids = request['service_area_ids']
    measurer_methods = config.get('measurer').keys()
    dataset_hint = request.get('dataset_hint', None)

    if request['method'] in measurer_methods:
        measurer_name = config.get('measurer')[request['method']]
    else:
        logger.warning(
            'Could not find measurer method {}. Defaulting to haversine.'.format(request['method'])
        )
        measurer_name = config.get('measurer')['haversine']

    # Exit early if there is no data.
    if not (provider_locations and service_area_ids):
        return []
    # If caching is enabled, return cached data.
    elif dataset_hint and config.get('cache_adequacy_requests'):
        return _get_cached_adequacy_response(
            dataset_hint=dataset_hint,
            measurer_name=measurer_name,
            service_area_ids=service_area_ids,
            locations=provider_locations,
            engine=engine,
        )
    else:
        return adequacy.calculate_adequacies(
            service_area_ids=service_area_ids,
            measurer_name=measurer_name,
            locations=provider_locations,
            engine=engine,
        )


def _get_cached_adequacy_response(
    dataset_hint,
    measurer_name,
    service_area_ids,
    locations,
    engine
):
    """
    Given a hint, return a cached adequacy response if one is available.

    If no response for the hint is available yet, calculate the adequacy and store for later use.
    """
    cache_filepath = _convert_dataset_hint_to_cached_filepath(dataset_hint, measurer_name)
    if os.path.isfile(cache_filepath):
        with open(cache_filepath, 'r') as f:
            response = json.load(f)
        logger.debug('Returning cached adequacy results.')
    else:
        response = adequacy.calculate_adequacies(
            engine=engine,
            service_area_ids=service_area_ids,
            measurer_name=measurer_name,
            locations=locations
        )
        logger.debug('Caching adequacy results.')
        with open(cache_filepath, 'w+') as f:
            json.dump(obj=response, fp=f)
    return response


def _convert_dataset_hint_to_cached_filepath(dataset_hint, measurer_name):
        dataset_name = 'adequacy_{}_{}.json'.format(dataset_hint, measurer_name)
        return os.path.join(DATASET_CACHE_DIRECTORY, dataset_name)
