"""Transformers for dataset (multi-example) operations, e.g., shuffling and batching.

These are mostly wrappers for standard tf.data.Dataset ops.
"""

import numpy as np
import tensorflow as tf
from sleap.nn.data.utils import expand_to_rank
import attr
from typing import List, Text, Optional


@attr.s(auto_attribs=True)
class Shuffler:
    """Shuffling transformer for use in pipelines.

    The input to this transformer should not be repeated or batched (though the latter
    would technically work). Repeating prevents the shuffling from going through "epoch"
    or "iteration" loops in the underlying dataset.

    Though batching before shuffling works and respects epoch boundaries, it is not
    recommended as it implies that the same examples will always be optimized for
    together within a mini-batch. This is not as effective for promoting generalization
    as element-wise shuffling which produces new combinations of elements within mini-
    batches.

    The ideal pipeline follows the order:
        shuffle -> batch -> repeat

    Attributes:
        shuffle: If False, returns the input dataset unmodified.
        buffer_size: Number of examples to keep in a buffer to sample uniformly from. If
            set too high, it may take a long time to fill the initial buffer, especially
            if it resets every epoch.
        reshuffle_each_iteration: If True, resets the sampling buffer every iteration
            through the underlying dataset.
    """

    shuffle: bool = True
    buffer_size: int = 64
    reshuffle_each_iteration: bool = True

    @property
    def input_keys(self) -> List[Text]:
        """Return the keys that incoming elements are expected to have."""
        return []

    @property
    def output_keys(self) -> List[Text]:
        """Return the keys that outgoing elements will have."""
        return []

    def transform_dataset(self, ds_input: tf.data.Dataset) -> tf.data.Dataset:
        """Create a dataset with shuffled element order.

        Args:
            ds_input: Any dataset.

        Returns:
            A `tf.data.Dataset` with elements containing the same keys, but in a
            shuffled order, if enabled.

            If the input dataset is repeated, this doesn't really respect epoch
            boundaries since it never reaches the end of the iterator.
        """
        if self.shuffle:
            return ds_input.shuffle(
                buffer_size=self.buffer_size,
                reshuffle_each_iteration=self.reshuffle_each_iteration
                )
        else:
            return ds_input


@attr.s(auto_attribs=True)
class Batcher:
    """Batching transformer for use in pipelines.

    This class enables variable-length example keys to be batched by converting them to
    ragged tensors prior to concatenation, then converting them back to dense tensors.

    See the notes in the `Shuffling` and `Repeater` transformers if training. If using
    in inference, this transformer will be used on its own without dropping remainders.

    The ideal (training) pipeline follows the order:
        shuffle -> batch -> repeat

    Attributes:
        batch_size: Number of elements within a batch. Every key will be stacked within
            their first axis (with expansion) such that it has `batch_size` length.
        drop_remainder: If True, final elements with fewer than `batch_size` examples
            will be dropped once the end of the input dataset iteration is reached. This
            should be True for training and False for inference.
    """

    batch_size: int = 8
    drop_remainder: bool = False

    @property
    def input_keys(self) -> List[Text]:
        """Return the keys that incoming elements are expected to have."""
        return []

    @property
    def output_keys(self) -> List[Text]:
        """Return the keys that outgoing elements will have."""
        return []

    def transform_dataset(self, ds_input: tf.data.Dataset) -> tf.data.Dataset:
        """Create a dataset with batched elements.

        Args:
            ds_input: Any dataset that produces dictionaries keyed by strings and values
                with any rank tensors.

        Returns:
            A `tf.data.Dataset` with elements containing the same keys, but with each
            tensor promoted to 1 rank higher (except for scalars with rank 0 will be
            promoted to rank 2).

            The keys of each element will contain `batch_size` individual elements
            stacked along the axis 0, such that length (`.shape[0]`) is equal to
            `batch_size`.

            Any keys that had variable length elements within the batch will be padded
            with NaNs to the size of the largest element's length for that key.
        """
        def expand(example):
            """Expand all keys to a minimum rank of 1."""
            for key in example:
                example[key] = expand_to_rank(example[key], target_rank=1, prepend=True)
            return example

        def unrag(example):
            """Convert all keys back to dense tensors NaN padded."""
            for key in example:
                example[key] = example[key].to_tensor(default_value=tf.cast(np.nan, example[key].dtype))
            return example

        # Ensure that all keys have a rank of at least 1 (i.e., scalars).
        ds_output = ds_input.map(expand, num_parallel_calls=tf.data.experimental.AUTOTUNE)

        # Batch elements as ragged tensors.
        ds_output = ds_output.apply(tf.data.experimental.dense_to_ragged_batch(batch_size=self.batch_size, drop_remainder=self.drop_remainder))

        # Convert elements back into dense tensors with padding.
        ds_output = ds_output.map(unrag, num_parallel_calls=tf.data.experimental.AUTOTUNE)

        return ds_output


@attr.s(auto_attribs=True)
class Repeater:
    """Repeating transformer for use in pipelines.

    Repeats the underlying elements indefinitely or for a number of "iterations" or
    "epochs".

    If placed before batching, this can create mini-batches with examples from across
    epoch boundaries.

    If placed after batching, this may never reach examples that are dropped as
    remainders if not shuffling.

    The ideal pipeline follows the order:
        shuffle -> batch -> repeat

    Attributes:
        repeat: If False, returns the input dataset unmodified.
        epochs: If -1, repeats the input dataset elements infinitely. Otherwise, loops
            through the elements of the input dataset this number of times.
    """

    repeat: bool = True
    epochs: int = -1

    @property
    def input_keys(self) -> List[Text]:
        """Return the keys that incoming elements are expected to have."""
        return []

    @property
    def output_keys(self) -> List[Text]:
        """Return the keys that outgoing elements will have."""
        return []

    def transform_dataset(self, ds_input: tf.data.Dataset) -> tf.data.Dataset:
        """Create a dataset with repeated loops over the input elements.

        Args:
            ds_input: Any dataset.

        Returns:
            A `tf.data.Dataset` with elements containing the same keys, but repeated for
            `epochs` iterations.
        """
        if self.repeat:
            return ds_input.repeat(count=self.epochs)
        else:
            return ds_input


@attr.s(auto_attribs=True)
class Prefetcher:
    """Prefetching transformer for use in pipelines.

    Prefetches elements from the input dataset to minimize the processing bottleneck
    as elements are requested since prefetching can occur in parallel.

    Attributes:
        prefetch: If False, returns the input dataset unmodified.
        buffer_size: Keep `buffer_size` elements loaded in the buffer. If set to -1
            (`tf.data.experimental.AUTOTUNE`), this value will be optimized
            automatically to decrease latency.
    """

    prefetch: bool = True
    buffer_size: int = tf.data.experimental.AUTOTUNE

    @property
    def input_keys(self) -> List[Text]:
        """Return the keys that incoming elements are expected to have."""
        return []

    @property
    def output_keys(self) -> List[Text]:
        """Return the keys that outgoing elements will have."""
        return []

    def transform_dataset(self, ds_input: tf.data.Dataset) -> tf.data.Dataset:
        """Create a dataset with prefetching to maintain a buffer during iteration.

        Args:
            ds_input: Any dataset.

        Returns:
            A `tf.data.Dataset` with identical elements. Processing that occurs with the
            elements that are produced can be done in parallel (e.g., training on the
            GPU) while new elements are generated from the pipeline.
        """
        if self.prefetch:
            return ds_input.prefetch(buffer_size=self.buffer_size)
        else:
            return ds_input
