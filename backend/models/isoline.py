"""All methods that create or fetch Isolines from different services."""
import json

from backend.models.time_distance_model import _miles_to_meters

import geopandas as gpd

import networkx as nx

import osmnx

import requests

from shapely import geometry


class Isoliner():
    """Base Isoliner class to be inherited from."""

    def __init__(self, api_url=None, api_key=None):
        """Initialize the isoliner class."""
        self.api_url = api_url
        self.api_key = api_key

    def get_single_isodistance_polygon(self, point, radius_in_miles):
        """Get an isodistance polygon for the given point and radius."""
        raise NotImplementedError('Isoline source must be specified.')


class OSMIsoliner(Isoliner):
    """Generic Isoliner class based on Open Street Maps."""

    def __init__(self, *args, **kwargs):
        """Instantiate an OSMIsoliner."""
        # TODO: Include graph as an attribute so that functions match interface specifications."""
        super(OSMIsoliner, self).__init__(*args, **kwargs)

    def get_single_isodistance_polygon(self, graph, point, radius_in_miles):
        """Given a point, return the isodistance polygon."""
        iso_nodes = self.get_isodistance_nodes(graph, point, radius_in_miles)
        # TODO: change this to concave hull.
        return gpd.GeoSeries(iso_nodes).unary_union.convex_hull

    def get_isodistance_nodes(self, graph, point, radius_in_miles):
        """Given a point and radius, return a bounding polygon of the isochorne in graph."""
        radius = _miles_to_meters(radius_in_miles)
        center_node = self._get_nearest_node(graph, point)
        subg = nx.ego_graph(graph, center_node, radius, distance='length')
        isodistance_nodes = [geometry.Point((d['x'], d['y'])) for node, d in subg.nodes(data=True)]
        return isodistance_nodes

    def _get_nearest_node(self, graph, point):
        """Given a point, return the nearest node in a graph."""
        return osmnx.get_nearest_node(graph, (point.y, point.x))


class MapBoxIsoliner(Isoliner):
    """Isoline class for MapBox API."""

    def __init__(self, *args, **kwargs):
        """Instantiate a MapBoxIsoliner."""
        super(MapBoxIsoliner, self).__init__(*args, **kwargs)

    def get_single_isodistance_polygon(self, point, radius_in_miles):
        """Get isodistance polygon for a given point at a given radius in miles."""
        # TODO: Implement this.
        pass


class MapzenIsoliner(Isoliner):
    """Isoline class for MapZen API."""

    def __init__(self, *args, **kwargs):
        """Instantiate a MapBoxIsoliner."""
        super(MapzenIsoliner, self).__init__(*args, **kwargs)
        self.api_url = 'http://matrix.mapzen.com/isochrone'

    def get_single_isochrone_polygon(self, point, time_in_minutes):
        """
        Return a GeoJSON blob containing the MapZen polygon isochrone around a given point.

        point: Shapely point to calculate times from.
        time: Time (in minutes) to calculate isochrone for. Defaults to 30 minutes.
        """
        json_params = {
            'locations': [
                {'lon': point.x, 'lat': point.y}
            ],
            'costing': 'auto',
            'contours': [{
                'time': time_in_minutes,
            }],
            'polygons': True
        }
        params = {
            'api_key': self.api_key,
            'json': json.dumps(json_params)
        }
        response = requests.get(self.api_url, params=params)
        response.raise_for_status()
        return response.json()['features'][0]

    def get_single_isodistance_polygon(self, point, radius_in_miles):
        """Get an isodistance polygon for a given point at a given radius in miles."""
        # TODO: Implement this
        pass
