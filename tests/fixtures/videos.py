import pytest

from sleap.io.video import Video

TEST_H5_FILE = "tests/data/hdf5_format_v1/training.scale=0.50,sigma=10.h5"
TEST_H5_DSET = "/box"
TEST_H5_CONFMAPS = "/confmaps"
TEST_H5_AFFINITY = "/pafs"
TEST_H5_INPUT_FORMAT = "channels_first"


@pytest.fixture
def hdf5_vid():
    return Video.from_hdf5(
        filename=TEST_H5_FILE, dataset=TEST_H5_DSET, input_format=TEST_H5_INPUT_FORMAT
    )


@pytest.fixture
def hdf5_confmaps():
    return Video.from_hdf5(
        filename=TEST_H5_FILE,
        dataset=TEST_H5_CONFMAPS,
        input_format=TEST_H5_INPUT_FORMAT,
    )


@pytest.fixture
def hdf5_affinity():
    return Video.from_hdf5(
        filename=TEST_H5_FILE,
        dataset=TEST_H5_AFFINITY,
        input_format=TEST_H5_INPUT_FORMAT,
        convert_range=False,
    )


TEST_SMALL_ROBOT_MP4_FILE = "tests/data/videos/small_robot.mp4"
TEST_SMALL_CENTERED_PAIR_VID = "tests/data/videos/centered_pair_small.mp4"


@pytest.fixture
def small_robot_mp4_vid():
    return Video.from_media(TEST_SMALL_ROBOT_MP4_FILE)


@pytest.fixture
def centered_pair_vid():
    return Video.from_media(TEST_SMALL_CENTERED_PAIR_VID)


TEST_SMALL_ROBOT_SIV_FILE0 = "tests/data/videos/robot0.jpg"
TEST_SMALL_ROBOT_SIV_FILE1 = "tests/data/videos/robot1.jpg"
TEST_SMALL_ROBOT_SIV_FILE2 = "tests/data/videos/robot2.jpg"
TEST_SMALL_ROBOT_VID = "tests/data/videos/small_robot_3_frame.mp4"


@pytest.fixture
def small_robot_single_image_vid():
    filenames = [
        TEST_SMALL_ROBOT_SIV_FILE0,
        TEST_SMALL_ROBOT_SIV_FILE1,
        TEST_SMALL_ROBOT_SIV_FILE2,
    ]
    return Video.from_image_filenames(filenames)


@pytest.fixture
def small_robot_3_frame_vid():
    filename = TEST_SMALL_ROBOT_VID
    return Video.from_filename(filename)
