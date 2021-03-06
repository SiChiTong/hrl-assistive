#ifndef PCL_SIFT_EXTRACTOR_H_
#define PCL_SIFT_EXTRACTOR_H_

#define USE_SIFT

// ROS
#include <ros/ros.h>
/* #include "tf/LinearMath/Transform.h" */
#include "tf/transform_listener.h"

#include "hrl_manipulation_task/robot.h"

// PCL
#include <pcl/point_cloud.h>
#include <pcl/point_types.h>
#include <pcl/PCLPointCloud2.h>
#include <pcl/conversions.h>
#include <pcl_conversions/pcl_conversions.h> 
#include <pcl/filters/conditional_removal.h> 
#include <pcl_ros/transforms.h>

#ifdef USE_SIFT
#include <pcl/keypoints/sift_keypoint.h>
#else
#include <pcl/tracking/pyramidal_klt.h>
#include <pcl/keypoints/harris_2d.h>
#endif

// Message
#include <sensor_msgs/PointCloud.h>
#include <sensor_msgs/PointCloud2.h>
#include <sensor_msgs/JointState.h>
#include <visualization_msgs/MarkerArray.h>
#include <visualization_msgs/Marker.h>

// Boost
#include <boost/thread.hpp>
/* #include <boost/math/distributions/normal.hpp> */

const float min_scale = 0.01;
const int nr_octaves = 3;
const int nr_scales = 3;
const float contrast = 10;

typedef pcl::PointXYZRGBA PointType;
typedef pcl::PointXYZI KeyType;
using namespace std;

class SIFT
{
public:
    SIFT(const ros::NodeHandle &nh);
    ~SIFT();

private:
    bool getParams();   
    bool initComms();
    bool initFilter();
    bool initRobot();

    void cameraCallback(const sensor_msgs::PointCloud2ConstPtr& input);
    void jointStateCallback(const sensor_msgs::JointStateConstPtr &jointState);

public:
    void pubSiftMarkers();
    void pubCoMMarkers(double x, double y, double z);
    void extractSIFT();

#ifdef USE_SIFT
#else
    void detect_keypoints (const CloudConstPtr& cloud);
#endif

    ros::Publisher sift_markers_pub_;
    ros::Publisher com_markers_pub_;

    ros::Subscriber camera_sub_;
    ros::Subscriber joint_state_sub_;

    EIGEN_MAKE_ALIGNED_OPERATOR_NEW

private:

    // Common major variables
    ros::NodeHandle nh_;
    boost::mutex camera_mtx; // mutex for contact cost subscribers

    // PCL
    pcl::PointCloud<PointType>::Ptr cloud_ptr_; 
    pcl::PointCloud<PointType>::Ptr cloud_filtered_ptr_; 
    pcl::PointCloud<PointType>::Ptr kpts_ptr_; 

#ifdef USE_SIFT
    // SIFT
    pcl::SIFTKeypoint<PointType, KeyType>::Ptr sift_;
#else
    // PyramidalKLT
    boost::shared_ptr<pcl::tracking::PyramidalKLTTracker<PointType> > tracker_;
    pcl::PointCloud<pcl::PointUV>::ConstPtr keypoints_;
    pcl::PointIndicesConstPtr points_status_;
#endif

    // tf
    tf::StampedTransform head_transform_;

    // filtering
    pcl::ConditionAnd<PointType>::Ptr range_cond_;

    // Robot
    boost::shared_ptr<Robot> robot_ptr_;
    std::string base_frame_;
    std::string ee_frame_;
    int robot_dimensions_; /// Number of dimensions in the robot space, eg 1->n 

    // current info
    sensor_msgs::JointState joint_state_;
    std::vector<std::string> joint_names_;
    std::vector<double> joint_angles_; // Current joint angles.
    bool has_current_;

    KDL::Frame current_ee_frame_;
    KDL::Frame current_wrist_frame_;
    KDL::Frame current_elbow_frame_;
    KDL::Frame current_shoulder_frame_;

    // flag
    bool has_tf_;
    bool has_joint_state_;

    boost::mutex cloud_mtx_; // mutex for contact cost subscribers
    boost::mutex points_mutex_;

};


/* long long getTimestamp(void) */
/* { */
/*     static __thread struct timeval tv; */
/*     gettimeofday(&tv, NULL); */
/*     return 1000000LL * tv.tv_sec + tv.tv_usec; */
/* } */



#endif

