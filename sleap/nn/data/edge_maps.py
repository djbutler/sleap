"""Transformers for generating edge confidence maps and part affinity fields."""

import numpy as np
import tensorflow as tf
import attr
from typing import List, Text, Optional, Tuple
import sleap
from sleap.nn.data.utils import (
    expand_to_rank,
    make_grid_vectors,
    gaussian_pdf,
    ensure_list,
)


def distance_to_edge(
    points: tf.Tensor, edge_source: tf.Tensor, edge_destination: tf.Tensor
) -> tf.Tensor:
    """Compute pairwise distance between points and undirected edges.

    Args:
        points: Tensor of dtype tf.float32 of shape (d_0, ..., d_n, 2) where the last
            axis corresponds to x- and y-coordinates. Distances will be broadcast across
            all point dimensions.
        edge_source: Tensor of dtype tf.float32 of shape (n_edges, 2) where the last
            axis corresponds to x- and y-coordinates of the source points of each edge.
        edge_destination: Tensor of dtype tf.float32 of shape (n_edges, 2) where the
            last axis corresponds to x- and y-coordinates of the source points of each
            edge.

    Returns:
        A tensor of dtype tf.float32 of shape (d_0, ..., d_n, n_edges) where the first
        axes correspond to the initial dimensions of `points`, and the last indicates
        the distance of each point to each edge.
    """
    # Ensure all points are at least rank 2.
    points = expand_to_rank(points, 2)
    edge_source = expand_to_rank(edge_source, 2)
    edge_destination = expand_to_rank(edge_destination, 2)

    # Compute number of point dimensions.
    n_pt_dims = tf.rank(points) - 1

    # Direction vector.
    direction_vector = edge_destination - edge_source  # (n_edges, 2)

    # Edge length.
    edge_length = tf.maximum(
        tf.reduce_sum(tf.square(direction_vector), axis=1), 1
    )  # (n_edges,)

    # Adjust query points relative to edge source point.
    source_relative_points = tf.expand_dims(points, axis=-2) - expand_to_rank(
        edge_source, n_pt_dims + 2
    )  # (..., n_edges, 2)

    # Project points to edge line.
    line_projections = tf.reduce_sum(
        source_relative_points * expand_to_rank(direction_vector, n_pt_dims + 2), axis=3
    ) / expand_to_rank(
        edge_length, n_pt_dims + 1
    )  # (..., n_edges)

    # Crop to line segment.
    line_projections = tf.clip_by_value(line_projections, 0, 1)  # (..., n_edges)

    # Compute distance from each point to the edge.
    distances = tf.reduce_sum(
        tf.square(
            (
                tf.expand_dims(line_projections, -1)
                * expand_to_rank(direction_vector, n_pt_dims + 2)
            )
            - source_relative_points
        ),
        axis=-1,
    )  # (..., n_edges)

    return distances


def make_edge_maps(
    xv: tf.Tensor,
    yv: tf.Tensor,
    edge_source: tf.Tensor,
    edge_destination: tf.Tensor,
    sigma: float,
) -> tf.Tensor:
    """Generate confidence maps for a set of undirected edges.

    Args:
        xv: Sampling grid vector for x-coordinates of shape (grid_width,) and dtype
            tf.float32. This can be generated by
            `sleap.nn.data.utils.make_grid_vectors`.
        yv: Sampling grid vector for y-coordinates of shape (grid_height,) and dtype
            tf.float32. This can be generated by
            `sleap.nn.data.utils.make_grid_vectors`.
        edge_source: Tensor of dtype tf.float32 of shape (n_edges, 2) where the last
            axis corresponds to x- and y-coordinates of the source points of each edge.
        edge_destination: Tensor of dtype tf.float32 of shape (n_edges, 2) where the
            last axis corresponds to x- and y-coordinates of the destination points of
            each edge.
        sigma: Standard deviation of the 2D Gaussian distribution sampled to generate
            confidence maps.

    Returns:
        A set of confidence maps corresponding to the probability of each point on a
        sampling grid being on each edge. These will be in a tensor of shape
        (grid_height, grid_width, n_edges) of dtype tf.float32.
    """
    sampling_grid = tf.stack(tf.meshgrid(xv, yv), axis=-1)  # (height, width, 2)
    distances = distance_to_edge(
        sampling_grid, edge_source=edge_source, edge_destination=edge_destination
    )
    edge_maps = gaussian_pdf(distances, sigma=sigma)
    return edge_maps


def make_pafs(
    xv: tf.Tensor,
    yv: tf.Tensor,
    edge_source: tf.Tensor,
    edge_destination: tf.Tensor,
    sigma: float,
) -> tf.Tensor:
    """Generate part affinity fields for a set of directed edges.

    Args:
        xv: Sampling grid vector for x-coordinates of shape (grid_width,) and dtype
            tf.float32. This can be generated by
            `sleap.nn.data.utils.make_grid_vectors`.
        yv: Sampling grid vector for y-coordinates of shape (grid_height,) and dtype
            tf.float32. This can be generated by
            `sleap.nn.data.utils.make_grid_vectors`.
        edge_source: Tensor of dtype tf.float32 of shape (n_edges, 2) where the last
            axis corresponds to x- and y-coordinates of the source points of each edge.
        edge_destination: Tensor of dtype tf.float32 of shape (n_edges, 2) where the
            last axis corresponds to x- and y-coordinates of the destination points of
            each edge.
        sigma: Standard deviation of the 2D Gaussian distribution sampled to generate
            the edge maps for masking the PAFs.

    Returns:
        A set of part affinity fields corresponding to the unit vector pointing along
        the direction of each edge weighted by the probability of each point on a
        sampling grid being on each edge. These will be in a tensor of shape
        (grid_height, grid_width, n_edges, 2) of dtype tf.float32. The last axis
        corresponds to the x- and y-coordinates of the unit vectors.
    """
    unit_vectors = edge_destination - edge_source
    unit_vectors = unit_vectors / tf.linalg.norm(unit_vectors, axis=-1, keepdims=True)
    edge_confidence_map = make_edge_maps(
        xv=xv,
        yv=yv,
        edge_source=edge_source,
        edge_destination=edge_destination,
        sigma=sigma,
    )
    pafs = tf.expand_dims(edge_confidence_map, axis=-1) * expand_to_rank(
        unit_vectors, 4
    )
    return pafs


def make_multi_pafs(
    xv: tf.Tensor,
    yv: tf.Tensor,
    edge_sources: tf.Tensor,
    edge_destinations: tf.Tensor,
    sigma: float,
) -> tf.Tensor:
    """Make multiple instance PAFs with max reduction.

    Args:
        xv: Sampling grid vector for x-coordinates of shape (grid_width,) and dtype
            tf.float32. This can be generated by
            `sleap.nn.data.utils.make_grid_vectors`.
        yv: Sampling grid vector for y-coordinates of shape (grid_height,) and dtype
            tf.float32. This can be generated by
            `sleap.nn.data.utils.make_grid_vectors`.
        edge_sources: Tensor of dtype tf.float32 of shape (n_instances, n_edges, 2)
            where the last axis corresponds to x- and y-coordinates of the source points
            of each edge.
        edge_destinations: Tensor of dtype tf.float32 of shape (n_instances, n_edges, 2)
            where the last axis corresponds to x- and y-coordinates of the destination
            points of each edge.
        sigma: Standard deviation of the 2D Gaussian distribution sampled to generate
            the edge maps for masking the PAFs.

    Returns:
        A set of part affinity fields generated for each instance. These will be in a
        tensor of shape (grid_height, grid_width, n_edges, 2). If multiple instance
        PAFs are defined on the same pixel, they will be summed.
    """
    grid_height = tf.shape(yv)[0]
    grid_width = tf.shape(xv)[0]
    n_edges = tf.shape(edge_sources)[1]
    n_instances = tf.shape(edge_sources)[0]

    pafs = tf.zeros((grid_height, grid_width, n_edges, 2), tf.float32)
    for i in range(n_instances):
        paf = make_pafs(
            xv=xv,
            yv=yv,
            edge_source=tf.gather(edge_sources, i, axis=0),
            edge_destination=tf.gather(edge_destinations, i, axis=0),
            sigma=sigma,
        )
        pafs += tf.where(tf.math.is_nan(paf), 0.0, paf)

    return pafs


def get_edge_points(
    instances: tf.Tensor, edge_inds: tf.Tensor
) -> Tuple[tf.Tensor, tf.Tensor]:
    """Return the points in each instance that form a directed graph.

    Args:
        instances: A tensor of shape (n_instances, n_nodes, 2) and dtype tf.float32
            containing instance points where the last axis corresponds to (x, y) pixel
            coordinates on the image. This must be rank-3 even if a single instance is
            present.
        edge_inds: A tensor of shape (n_edges, 2) and dtype tf.int32 containing the node
            indices that define a directed graph, where the last axis corresponds to the
            source and destination node indices.

    Returns:
        Tuple of (edge_sources, edge_destinations) containing the edge and destination
        points respectively. Both will be tensors of shape (n_instances, n_edges, 2),
        where the last axis corresponds to (x, y) pixel coordinates on the image.
    """
    source_inds = tf.cast(tf.gather(edge_inds, 0, axis=1), tf.int32)
    destination_inds = tf.cast(tf.gather(edge_inds, 1, axis=1), tf.int32)
    edge_sources = tf.gather(instances, source_inds, axis=1)
    edge_destinations = tf.gather(instances, destination_inds, axis=1)
    return edge_sources, edge_destinations


@attr.s(auto_attribs=True)
class PartAffinityFieldsGenerator:
    """Transformer to generate part affinity fields.

    Attributes:
        sigma: Standard deviation of the 2D Gaussian distribution sampled to weight the
            part affinity fields by their distance to the edges. This defines the spread
            in units of the input image's grid, i.e., it does not take scaling in
            previous steps into account.
        output_stride: Relative stride of the generated confidence maps. This is
            effectively the reciprocal of the output scale, i.e., increase this to
            generate confidence maps that are smaller than the input images.
        skeletons: List of `sleap.Skeleton`s to use for looking up the index of the
            edges.
        flatten_channels: If False, the generated tensors are of shape
            [height, width, n_edges, 2]. If True, generated tensors are of shape
            [height, width, n_edges * 2] by flattening the last 2 axes.
    """

    sigma: float = attr.ib(default=1.0, converter=float)
    output_stride: int = attr.ib(default=1, converter=int)
    skeletons: Optional[List[sleap.Skeleton]] = attr.ib(
        default=None, converter=attr.converters.optional(ensure_list)
    )
    flatten_channels: bool = False

    @property
    def input_keys(self) -> List[Text]:
        """Return the keys that incoming elements are expected to have."""
        return ["image", "instances", "skeleton_inds"]

    @property
    def output_keys(self) -> List[Text]:
        """Return the keys that outgoing elements will have."""
        return self.input_keys + ["part_affinity_fields"]

    def transform_dataset(self, input_ds: tf.data.Dataset) -> tf.data.Dataset:
        """Create a dataset that contains the generated confidence maps.

        Args:
            input_ds: A dataset with elements that contain the keys "image",
                "instances" and "skeleton_inds".

        Returns:
            A `tf.data.Dataset` with the same keys as the input, as well as
            "part_affinity_fields".

            The "part_affinity_fields" key will be a tensor of shape
            (grid_height, grid_width, n_edges, 2) containing the combined part affinity
            fields of all instances in the frame.

            If the `flatten_channels` attribute is set to True, the last 2 axes of the
            "part_affinity_fields" are flattened to produce a tensor of shape
            (grid_height, grid_width, n_edges * 2). This is a convenient form when
            training models as a rank-4 (batched) tensor will generally be expected.

        Notes:
            The output stride is relative to the current scale of the image. To map
            points on the part affinity fields to the raw image, first multiply them by
            the output stride, and then scale the x- and y-coordinates by the "scale"
            key.

            Importantly, the sigma will be proportional to the current image grid, not
            the original grid prior to scaling operations.
        """
        # Infer image dimensions to generate sampling grid.
        test_example = next(iter(input_ds))
        image_height = test_example["image"].shape[0]
        image_width = test_example["image"].shape[1]

        # Generate sampling grid vectors.
        xv, yv = make_grid_vectors(
            image_height=image_height,
            image_width=image_width,
            output_stride=self.output_stride,
        )
        grid_height = len(yv)
        grid_width = len(xv)

        # Pull out edge indices.
        # TODO: Multi-skeleton support.
        edge_inds = tf.cast(self.skeletons[0].edge_inds, dtype=tf.int32)
        n_edges = len(edge_inds)

        def generate_pafs(example):
            """Local processing function for dataset mapping."""
            instances = example["instances"]
            in_img = (instances > 0) & (
                instances < tf.reshape(tf.stack([xv[-1], yv[-1]], axis=0), [1, 1, 2])
            )
            in_img = tf.reduce_any(tf.reduce_all(in_img, axis=-1), axis=1)
            in_img = tf.ensure_shape(in_img, [None])
            instances = tf.boolean_mask(instances, in_img)

            edge_sources, edge_destinations = get_edge_points(instances, edge_inds)
            edge_sources = tf.ensure_shape(edge_sources, (None, n_edges, 2))
            edge_destinations = tf.ensure_shape(edge_destinations, (None, n_edges, 2))

            pafs = make_multi_pafs(
                xv=xv,
                yv=yv,
                edge_sources=edge_sources,
                edge_destinations=edge_destinations,
                sigma=self.sigma,
            )
            pafs = tf.ensure_shape(pafs, (grid_height, grid_width, n_edges, 2))

            if self.flatten_channels:
                pafs = tf.reshape(pafs, [grid_height, grid_width, n_edges * 2])
                pafs = tf.ensure_shape(pafs, (grid_height, grid_width, n_edges * 2))

            example["part_affinity_fields"] = pafs

            return example

        # Map transformation.
        output_ds = input_ds.map(
            generate_pafs, num_parallel_calls=tf.data.experimental.AUTOTUNE
        )
        return output_ds
