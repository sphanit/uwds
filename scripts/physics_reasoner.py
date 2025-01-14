#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import rospy
import pybullet as p
import numpy as np
from tf import transformations as tf
import math
import uuid
from pyuwds.reconfigurable_client import ReconfigurableClient
from uwds_msgs.msg import Changes, Situation, Property, Invalidations
from pyuwds.uwds import FILTER
from pyuwds.types.nodes import MESH
from pyuwds.types.situations import ACTION, FACT
from std_msgs.msg import Header

PLACED = 0
HELD = 1
RELEASED = 2

PLACE_CONFIDENCE = 0.85
PICK_CONFIDENCE = 0.85
RELEASE_CONFIDENCE = 0.85

IN_CONFIDENCE = 0.65
ONTOP_CONFIDENCE = 0.95

EPSILON = 0.015  # 1cm

class PhysicsReasoner(ReconfigurableClient):
    """
    """
    def __init__(self):
        """
        """
        self.ressource_folder = rospy.get_param("~ressource_folder")

        # reasoning parameters
        self.infer_actions = rospy.get_param("~infer_actions", True)
        self.perception_duration = rospy.get_param("~perception_duration", 0.9)
        self.simulation_tolerance = rospy.get_param("~simulation_tolerance", 0.045)
        self.perception_tolerance = rospy.get_param("~perception_tolerance", 0.01)
        gui = rospy.get_param("~use_gui", False)
        # simulator parameters
        self.time_step = rospy.get_param("~time_step", 1.0/240)
        self.reasoning_frequency = rospy.get_param("~reasoning_frequency", 20)
        self.simulation_step = rospy.get_param("~simulation_step", 0.1)
        # self.nb_step_fall = int(self.fall_simulation_step / self.time_step)
        self.nb_step = int(self.simulation_step / self.time_step)
        # init simulator
        if gui is True:
            p.connect(p.GUI)
        else:
            p.connect(p.DIRECT)
        p.setGravity(0, 0, -10)
        #p.setPhysicsEngineParameter(contactBreakingThreshold=0.01)
        p.setAdditionalSearchPath(self.ressource_folder)
        p.setTimeStep(self.time_step)
        p.setPhysicsEngineParameter(fixedTimeStep=self.time_step)

        self.bullet_node_id_map = {}
        self.previous_placed_positions = {}

        self.corrected_position = {}
        self.corrected_orientation = {}
        self.corrected_linear_velocity = {}
        self.corrected_angular_velocity = {}

        self.perceived_position = {}
        self.perceived_orientation = {}
        self.perceived_linear_velocity = {}
        self.perceived_angular_velocity = {}

        self.previous_position = {}
        self.previous_orientation = {}

        self.node_action_state = {}
        self.place_confidence = {}
        self.pick_confidence = {}
        self.release_confidence = {}
        self.isontop_confidence = {}
        self.isin_confidence = {}

        self.invalidation_time = {}

        self.max_step = 10

        self.simulated_node_ids = []
        self.previous_perceived_position = {}
        self.previous_perceived_orientation = {}

        self.isPerceived = {}
        self.isUnstable = {}
        self.isMoving = {}

        self.isIn = {}
        self.isOnTop = {}
        self.isContaining = {}

        super(PhysicsReasoner, self).__init__("gravity_filter", FILTER)

        self.timer = rospy.Timer(rospy.Duration(1.0/self.reasoning_frequency), self.reasoningCallback)

    def onReconfigure(self, worlds_names):
        """
        """
        pass

    def onSubscribeChanges(self, world_name):
        """
        """
        pass

    def onUnsubscribeChanges(self, world_name):
        """
        """
        pass

    def onChanges(self, world_name, header, invalidations):
        """
        """
        now = rospy.Time.now()

        for node_id in invalidations.node_ids_deleted:
            if node_id in self.perceived_position:
                del self.perceived_position[node_id]
            if node_id in self.perceived_orientation:
                del self.perceived_orientation[node_id]
            if node_id in self.perceived_linear_velocity:
                del self.perceived_linear_velocity[node_id]
            if node_id in self.perceived_angular_velocity:
                del self.perceived_angular_velocity[node_id]
            if node_id in self.previous_perceived_position:
                del self.previous_perceived_position[node_id]
            if node_id in self.previous_perceived_orientation:
                del self.previous_perceived_orientation[node_id]
            if node_id in self.isContaining:
                del self.isContaining[node_id]
            if node_id in self.isUnstable:
                del self.isUnstable[node_id]
            if node_id in self.isPerceived:
                del self.isPerceived[node_id]
            if node_id in self.node_action_state:
                del self.node_action_state[node_id]


        for node_id in invalidations.node_ids_updated:
            node = self.ctx.worlds()[world_name].scene().nodes()[node_id]
            if node.type == MESH:
                self.invalidation_time[node_id] = now
                if node_id not in self.isContaining:
                    self.isContaining[node_id] = {}
                if node_id not in self.isUnstable:
                    self.isUnstable[node_id] = False
                if node_id in self.perceived_position:
                    self.previous_perceived_position[node_id] = self.perceived_position[node_id]
                if node_id in self.perceived_orientation:
                    self.previous_perceived_orientation[node_id] = self.perceived_orientation[node_id]

                self.perceived_position[node_id] = [node.position.pose.position.x, node.position.pose.position.y, node.position.pose.position.z]
                self.perceived_orientation[node_id] = [node.position.pose.orientation.x, node.position.pose.orientation.y, node.position.pose.orientation.z, node.position.pose.orientation.w]
                self.perceived_linear_velocity[node_id] = [node.velocity.twist.linear.x, node.velocity.twist.linear.y, node.velocity.twist.linear.z]
                self.perceived_angular_velocity[node_id] = [node.velocity.twist.angular.x, node.velocity.twist.angular.y, node.velocity.twist.angular.z]
                update = False
                if node_id in self.previous_perceived_position:
                    if self.isUnstable[node_id] is False:
                        if not(np.allclose(self.previous_perceived_position[node_id], self.perceived_position[node_id], atol=self.perception_tolerance) \
                                and np.allclose(self.previous_perceived_orientation[node_id], self.perceived_orientation[node_id], atol=self.perception_tolerance)):
                            self.updateBulletNode(world_name, node_id, self.perceived_position[node_id], self.perceived_orientation[node_id], self.perceived_linear_velocity[node_id], self.perceived_angular_velocity[node_id])
                            update = True
                    else:
                        self.updateBulletNode(world_name, node_id, self.perceived_position[node_id], self.perceived_orientation[node_id], self.perceived_linear_velocity[node_id], self.perceived_angular_velocity[node_id])
                        update = True
                else:
                    self.updateBulletNode(world_name, node_id, self.perceived_position[node_id], self.perceived_orientation[node_id], self.perceived_linear_velocity[node_id], self.perceived_angular_velocity[node_id])
                    update = True
                if update:
                    for object_id in self.isContaining[node_id]:
                        object = self.ctx.worlds()[world_name].scene().nodes()[object_id]
                        if node_id in self.previous_position and object_id in self.previous_position:
                            if node_id in self.previous_position and object_id in self.previous_position:
                                #t_prev = tf.compose_matrix(angles=tf.euler_from_quaternion(self.previous_orientation[node_id], axes='sxyz'), translate=self.previous_position[node_id])
                                #t_perceived = tf.compose_matrix(angles=tf.euler_from_quaternion(self.perceived_orientation[node_id], axes='sxyz'), translate=self.perceived_position[node_id])
                                t_prev = tf.translation_matrix(self.previous_position[node_id])
                                t_perceived = tf.translation_matrix(self.perceived_position[node_id])
                                offset = tf.translation_from_matrix(np.dot(np.linalg.inv(t_prev), t_perceived))
                                if not np.allclose(offset, [0, 0, 0], atol=0.01):
                                    object_position = self.previous_position[object_id]
                                    object_orientation = self.previous_orientation[object_id]
                                    object_position = [object_position[0]+offset[0], object_position[1]+offset[1], object_position[2]+offset[2]]
                                    self.updateBulletNode(world_name, object_id, object_position, object_orientation, self.perceived_linear_velocity[node_id], self.perceived_angular_velocity[node_id])

    def reasoningCallback(self, timer):
        header = Header()
        header.stamp = rospy.Time.now()
        if len(self.input_worlds)>0:
            world_name = self.input_worlds[0]
            invalidations = Invalidations()
            changes = self.filter(world_name, header, invalidations)
            self.ctx.worlds()[world_name+"_stable"].update(changes, header)

    def filter(self, world_name, header, invalidations):
        """
        """
        #print "start reasoning"
        start_reasoning_time = rospy.Time.now()
        changes = Changes()

        for mesh_id in invalidations.mesh_ids_updated:
            changes.meshes_to_update.append(self.meshes()[mesh_id])

        for situation_id in invalidations.situation_ids_updated:
            changes.situations_to_update.append(self.meshes()[mesh_id])

        for node in self.ctx.worlds()[world_name].scene().nodes():
            if node.type == MESH:
                if node.id in self.invalidation_time:
                    self.isPerceived[node.id] = (header.stamp - self.invalidation_time[node.id]) < rospy.Duration(self.perception_duration)
                else:
                    self.isPerceived[node.id] = True

        start_fall_reasoning_time = rospy.Time.now()
        for node_id in self.simulated_node_ids:
            self.isUnstable[node_id] = False

        for i in range(0, self.nb_step):
            p.stepSimulation()
            for node_id in self.simulated_node_ids:
                if self.isPerceived[node_id]:
                    node = self.ctx.worlds()[world_name].scene().nodes()[node_id]

                    infered_position, infered_orientation = p.getBasePositionAndOrientation(self.bullet_node_id_map[node_id])
                    infered_linear_velocity, infered_angular_velocity = p.getBaseVelocity(self.bullet_node_id_map[node_id])
                    perceived_position = self.perceived_position[node_id]
                    stability_distance = math.sqrt(pow(perceived_position[0]-infered_position[0], 2) + pow(perceived_position[1]-infered_position[1], 2) + pow(perceived_position[2]-infered_position[2], 2))
                    is_unstable = stability_distance > self.simulation_tolerance
                    if self.isUnstable[node_id] is False and is_unstable:
                        self.isUnstable[node_id] = True
                        #print node.name + " is unstable after "+str(i)+"/"+str(self.nb_step)+" steps"
                        for object_id in self.isContaining[node_id]:
                            if object_id in self.perceived_position:
                                t_perceived = tf.translation_matrix(self.perceived_position[node_id])
                                t_infered = tf.translation_matrix(infered_position)
                                offset = tf.translation_from_matrix(np.dot(np.linalg.inv(t_infered), t_perceived))
                                #if not np.allclose(offset, [0, 0, 0], atol=0.1):
                                object_position, object_orientation = p.getBasePositionAndOrientation(self.bullet_node_id_map[object_id])
                                object_position = [object_position[0]+offset[0], object_position[1]+offset[1], object_position[2]+offset[2]]
                                self.updateBulletNode(world_name, object_id, object_position, object_orientation, self.perceived_linear_velocity[node_id], self.perceived_angular_velocity[node_id])
                    if self.isUnstable[node_id]:
                        self.updateBulletNode(world_name, node_id, self.perceived_position[node_id], self.perceived_orientation[node_id], self.perceived_linear_velocity[node_id], self.perceived_angular_velocity[node_id])

        end_fall_reasoning_time = rospy.Time.now()

        for node in self.ctx.worlds()[world_name].scene().nodes():
            # print len(self.simulated_node_ids)
            if node.id in self.simulated_node_ids:
                if self.isUnstable[node.id] is True and self.isPerceived[node.id] is True:
                    if (self.node_action_state[node.id] == PLACED or self.node_action_state[node.id] == RELEASED) and self.infer_actions and self.pick_confidence[node_id] > PICK_CONFIDENCE:
                        print node.name + " picked up"
                        situation = Situation()
                        situation.id = str(uuid.uuid4().hex)
                        situation.type = ACTION
                        situation.description = node.name + " picked up"
                        situation.confidence = PICK_CONFIDENCE
                        situation.start.data = header.stamp
                        situation.end.data = header.stamp
                        situation.properties.append(Property("subject", node.id))
                        situation.properties.append(Property("action", "Place"))
                        changes.situations_to_update.append(situation)
                        self.node_action_state[node.id] = HELD
                    self.pick_confidence[node.id] = self.pick_confidence[node.id]*(1+PICK_CONFIDENCE)
                    #print self.pick_confidence[node_id]
                    if self.pick_confidence[node.id] > 1.0: self.pick_confidence[node.id] = 1.0
                    self.place_confidence[node.id] = self.place_confidence[node.id]*(1-PICK_CONFIDENCE)
                    if self.place_confidence[node.id] < .1: self.place_confidence[node.id] = 0.1
                    node.position.pose.position.x = self.perceived_position[node.id][0]
                    node.position.pose.position.y = self.perceived_position[node.id][1]
                    node.position.pose.position.z = self.perceived_position[node.id][2]
                    node.position.pose.orientation.x = self.perceived_orientation[node.id][0]
                    node.position.pose.orientation.y = self.perceived_orientation[node.id][1]
                    node.position.pose.orientation.z = self.perceived_orientation[node.id][2]
                    node.position.pose.orientation.w = self.perceived_orientation[node.id][3]
                    node.velocity.twist.linear.x = self.perceived_linear_velocity[node.id][0]
                    node.velocity.twist.linear.y = self.perceived_linear_velocity[node.id][1]
                    node.velocity.twist.linear.z = self.perceived_linear_velocity[node.id][2]
                    node.velocity.twist.angular.x = self.perceived_angular_velocity[node.id][0]
                    node.velocity.twist.angular.y = self.perceived_angular_velocity[node.id][1]
                    node.velocity.twist.angular.z = self.perceived_angular_velocity[node.id][2]
                    self.previous_position[node.id] = self.perceived_position[node.id]
                    self.previous_orientation[node.id] = self.perceived_orientation[node.id]
                    self.ctx.worlds()[world_name].scene().nodes()[node.id]=node
                    changes.nodes_to_update.append(node)
                else:
                    if node.id in self.node_action_state:
                        if self.node_action_state[node.id] == HELD and self.infer_actions:
                            if self.isPerceived[node.id]:
                                self.place_confidence[node.id] = self.place_confidence[node.id]*(1+PLACE_CONFIDENCE)
                                if self.place_confidence[node.id] > 1.0: self.place_confidence[node.id] = 1.0

                                self.pick_confidence[node.id] = self.pick_confidence[node.id]*(1-PLACE_CONFIDENCE)
                                if self.pick_confidence[node.id] < .1: self.pick_confidence[node.id] = 0.1

                                self.release_confidence[node.id] = self.release_confidence[node.id]*(1-RELEASE_CONFIDENCE)
                                if self.release_confidence[node.id] < .1: self.release_confidence[node.id] = 0.1

                                if self.place_confidence[node.id] > PLACE_CONFIDENCE:
                                    print node.name + " placed"
                                    situation = Situation()
                                    situation.id = str(uuid.uuid4().hex)
                                    situation.type = ACTION
                                    situation.description = node.name + " placed"
                                    situation.confidence = PLACE_CONFIDENCE
                                    situation.start.data = header.stamp
                                    situation.end.data = header.stamp
                                    situation.properties.append(Property("subject", node.id))
                                    situation.properties.append(Property("action", "Pick"))
                                    changes.situations_to_update.append(situation)
                                    self.node_action_state[node.id] = PLACED
                            else:
                                self.release_confidence[node.id] = self.release_confidence[node.id]*(1+RELEASE_CONFIDENCE)
                                if self.release_confidence[node.id] > 1.0: self.release_confidence[node.id] = 1.0

                                self.pick_confidence[node.id] = self.pick_confidence[node.id]*(1-PLACE_CONFIDENCE)
                                if self.pick_confidence[node.id] < .1: self.pick_confidence[node.id] = 0.1

                                self.place_confidence[node.id] = self.place_confidence[node.id]*(1-PICK_CONFIDENCE)
                                if self.place_confidence[node.id] < .1: self.place_confidence[node.id] = 0.1

                                if self.release_confidence[node.id] > RELEASE_CONFIDENCE:
                                    print node.name + " released"
                                    situation = Situation()
                                    situation.id = str(uuid.uuid4().hex)
                                    situation.type = ACTION
                                    situation.description = node.name + " released"
                                    situation.confidence = RELEASE_CONFIDENCE
                                    situation.start.data = header.stamp
                                    situation.end.data = header.stamp
                                    situation.properties.append(Property("subject", node.id))
                                    situation.properties.append(Property("action", "Release"))
                                    changes.situations_to_update.append(situation)
                                    self.node_action_state[node.id] = RELEASED
                    infered_position, infered_orientation = p.getBasePositionAndOrientation(self.bullet_node_id_map[node.id])
                    infered_linear_velocity, infered_angular_velocity = p.getBaseVelocity(self.bullet_node_id_map[node.id])
                    x, y, z = infered_position
                    node.position.pose.position.x = x
                    node.position.pose.position.y = y
                    node.position.pose.position.z = z
                    x, y, z, w = infered_orientation
                    node.position.pose.orientation.x = x
                    node.position.pose.orientation.y = y
                    node.position.pose.orientation.z = z
                    node.position.pose.orientation.w = w
                    x, y, z = infered_linear_velocity
                    node.velocity.twist.linear.x = x
                    node.velocity.twist.linear.y = y
                    node.velocity.twist.linear.z = z
                    x, y, z = infered_angular_velocity
                    node.velocity.twist.angular.x = x
                    node.velocity.twist.angular.y = y
                    node.velocity.twist.angular.z = z
                    self.previous_position[node.id] = infered_position
                    self.previous_orientation[node.id] = infered_orientation
                    self.ctx.worlds()[world_name].scene().nodes()[node.id]=node
                    changes.nodes_to_update.append(node)
            else:
                changes.nodes_to_update.append(node)

        # for contact in p.getContactPoints():
        #     pass

        now = rospy.Time.now()
        for node1_id in self.simulated_node_ids:
            node1 = self.ctx.worlds()[world_name].scene().nodes()[node1_id]
            if node1.type != MESH:
                continue
            for node2_id in self.simulated_node_ids:
                node2 = self.ctx.worlds()[world_name].scene().nodes()[node2_id]
                if node1.id == node2.id:
                    continue
                if node2.type != MESH:
                    continue
                bb1 = self.aabb(node1)
                bb2 = self.aabb(node2)
                if node1.id not in self.isIn:
                    self.isIn[node1.id] = {}
                if node1.id not in self.isOnTop:
                    self.isOnTop[node1.id] = {}
                if node2.id not in self.isContaining:
                    self.isContaining[node2.id] = {}
                if self.isin(bb1, bb2, node2.id in self.isIn[node1.id]):
                    if node2.id not in self.isIn[node1.id]:
                        sit = Situation()
                        sit.id = str(uuid.uuid4())
                        sit.type = FACT
                        sit.description = node1.name + " is in " + node2.name
                        sit.properties.append(Property("subject", node1.id))
                        sit.properties.append(Property("object", node2.id))
                        sit.properties.append(Property("predicate", "isIn"))
                        sit.confidence = IN_CONFIDENCE
                        sit.start.data = now
                        sit.end.data = rospy.Time(0)
                        self.isIn[node1.id][node2.id] = sit
                        self.isContaining[node2.id][node1.id] = sit
                        changes.situations_to_update.append(sit)
                else:
                    if node2.id in self.isIn[node1.id]:
                        self.isIn[node1.id][node2.id].end.data = now
                        self.isIn[node1.id][node2.id].description = node1.name + " was in " + node2.name
                        sit = self.isIn[node1.id][node2.id]
                        changes.situations_to_update.append(sit)
                        del self.isIn[node1.id][node2.id]
                        del self.isContaining[node2.id][node1.id]

                if self.isontop(bb1, bb2, node2.id in self.isOnTop[node1.id]):
                    if node2.id not in self.isOnTop[node1.id]:
                        sit = Situation()
                        sit.id = str(uuid.uuid4())
                        sit.type = FACT
                        sit.description = node1.name + " is on " + node2.name
                        sit.properties.append(Property("subject", node1.id))
                        sit.properties.append(Property("object", node2.id))
                        sit.properties.append(Property("predicate", "isOn"))
                        sit.confidence = ONTOP_CONFIDENCE
                        sit.start.data = now
                        sit.end.data = rospy.Time(0)
                        self.isOnTop[node1.id][node2.id] = sit
                        changes.situations_to_update.append(sit)
                else:
                    if node2.id in self.isOnTop[node1.id]:
                        self.isOnTop[node1.id][node2.id].description = node1.name + " was on " + node2.name
                        self.isOnTop[node1.id][node2.id].end.data = now
                        sit = self.isOnTop[node1.id][node2.id]
                        changes.situations_to_update.append(sit)
                        del self.isOnTop[node1.id][node2.id]

        end_reasoning_time = rospy.Time.now()
        if (1.0/(end_reasoning_time - start_reasoning_time).to_sec() < self.reasoning_frequency*0.5):
            rospy.logwarn("[%s::filter] reasoning too slow ! %f", self.ctx.name(), 1.0/(end_reasoning_time - start_reasoning_time).to_sec())
        return changes

    def updateBulletNode(self, world_name, node_id, position, orientation, linear, angular):
        """
        """
        if self.ctx.worlds()[world_name].scene().root_id() not in self.bullet_node_id_map:
            self.bullet_node_id_map[self.ctx.worlds()[world_name].scene().root_id()] = p.loadURDF("plane.urdf")

        node = self.ctx.worlds()[world_name].scene().nodes()[node_id]
        if node_id not in self.bullet_node_id_map:
            try:
                label = node.name.replace("_"," ").replace("."," ").replace("-"," ").lower()
                result = []
                for word in label.split(" "):
                    try:
                        test = int(word)
                    except ValueError:
                        result.append(word)
                first = True
                for word in result:
                    if first is True:
                        label = word
                        first = False
                    else:
                        label += "_" + word
                self.bullet_node_id_map[node_id] = p.loadURDF(label+".urdf", position, orientation)
                rospy.loginfo("[%s::updateBulletNodeNodes] "+label+".urdf' loaded successfully", self.ctx.name())
                p.changeDynamics(self.bullet_node_id_map[node_id], -1, rollingFriction=0.9, spinningFriction=0.9)
                self.simulated_node_ids.append(node_id)
                if node_id not in self.node_action_state:
                    self.node_action_state[node_id] = PLACED
                    self.place_confidence[node_id] = 1.0
                    self.pick_confidence[node_id] = 0.1
                    self.release_confidence[node_id] = 0.1
            except Exception as e:
                self.bullet_node_id_map[node_id] = -1
                rospy.logwarn("[%s::updateBulletNodeNodes] "+str(e))
        if self.bullet_node_id_map[node_id] > 0:
            p.resetBaseVelocity(self.bullet_node_id_map[node_id], linear, angular)
            p.resetBasePositionAndOrientation(self.bullet_node_id_map[node_id], position, orientation)
        else:
            self.bullet_node_id_map[node_id] = -1

    def aabb(self, node):
        """
        Compute world aabb by transforming the corners of the aabb by the node pose
        """
        for property in node.properties:
            if property.name == "aabb":
                aabb = property.data.split(",")
                if len(aabb) == 3:
                    t = [node.position.pose.position.x, node.position.pose.position.y, node.position.pose.position.z]
                    q = [node.position.pose.orientation.x, node.position.pose.orientation.y, node.position.pose.orientation.z, node.position.pose.orientation.w]
                    trans = tf.translation_matrix(t)
                    rot = tf.quaternion_matrix(q)
                    transform = tf.concatenate_matrices(trans, rot)
                    v = []
                    v.append(tf.translation_from_matrix(np.dot(transform, tf.translation_matrix([ float(aabb[0])/2,  float(aabb[1])/2, float(aabb[2])/2]))))
                    v.append(tf.translation_from_matrix(np.dot(transform, tf.translation_matrix([-float(aabb[0])/2,  float(aabb[1])/2, float(aabb[2])/2]))))
                    v.append(tf.translation_from_matrix(np.dot(transform, tf.translation_matrix([ float(aabb[0])/2, -float(aabb[1])/2, float(aabb[2])/2]))))
                    v.append(tf.translation_from_matrix(np.dot(transform, tf.translation_matrix([-float(aabb[0])/2, -float(aabb[1])/2, float(aabb[2])/2]))))
                    v.append(tf.translation_from_matrix(np.dot(transform, tf.translation_matrix([ float(aabb[0])/2,  float(aabb[1])/2, -float(aabb[2])/2]))))
                    v.append(tf.translation_from_matrix(np.dot(transform, tf.translation_matrix([-float(aabb[0])/2,  float(aabb[1])/2, -float(aabb[2])/2]))))
                    v.append(tf.translation_from_matrix(np.dot(transform, tf.translation_matrix([ float(aabb[0])/2, -float(aabb[1])/2, -float(aabb[2])/2]))))
                    v.append(tf.translation_from_matrix(np.dot(transform, tf.translation_matrix([-float(aabb[0])/2, -float(aabb[1])/2, -float(aabb[2])/2]))))
                    bb_min = [1e10, 1e10, 1e10]
                    bb_max = [-1e10, -1e10, -1e10]
                    for vertex in v:
                        bb_min = np.minimum(bb_min, vertex)
                        bb_max = np.maximum(bb_max, vertex)
                    return bb_min, bb_max
        raise RuntimeError("aabb not present")

    def bb_footprint(self, bb):
        """
        Copied from severin lemaignan underworlds client example :
        see : https://github.com/severin-lemaignan/underworlds/blob/master/clients/spatial_relations.py
        """
        x1, y1, z1 = bb[0]
        x2, y2, z2 = bb[1]

        return (x1, y1), (x2, y2)

    def overlap(self, rect1, rect2):
        """Overlapping rectangles overlap both horizontally & vertically
        Coped from severin lemaignan underworlds client example :
        see : https://github.com/severin-lemaignan/underworlds/blob/master/clients/spatial_relations.py
        """
        (l1, b1), (r1, t1) = rect1
        (l2, b2), (r2, t2) = rect2
        return self.range_overlap(l1, r1, l2, r2) and self.range_overlap(b1, t1, b2, t2)

    def range_overlap(self, a_min, a_max, b_min, b_max):
        """Neither range is completely greater than the other

        http://codereview.stackexchange.com/questions/31352/overlapping-rectangles
        Modified from severin lemaignan underworlds client example :
        see : https://github.com/severin-lemaignan/underworlds/blob/master/clients/spatial_relations.py
        """
        return (a_min <= b_max) and (b_min <= a_max)

    def weakly_cont(self, rect1, rect2, prev=False):
        """Obj1 is weakly contained if the base of the object is surrounded
        by Obj2
        Modified from severin lemaignan underworlds client example :
        see : https://github.com/severin-lemaignan/underworlds/blob/master/clients/spatial_relations.py
        """
        (l1, b1), (r1, t1) = rect1
        (l2, b2), (r2, t2) = rect2
        if prev is False:
            return (l1 - 2*EPSILON >= l2) and (b1 - 2*EPSILON >= b2) and (r1 - 2*EPSILON <= r2) and (t1 - 2*EPSILON <= t2)
        else:
            return (l1 + 2*EPSILON >= l2) and (b1 + 2*EPSILON >= b2) and (r1 + 2*EPSILON <= r2) and (t1 + 2*EPSILON <= t2)

    def isabove(self, bb1, bb2, prev=False):
        """
        For obj 1 to be above obj 2:
        - the bottom of its bounding box must be higher that
          the top of obj 2's bounding box
        - the bounding box footprint of both objects must overlap
        Modified from severin lemaignan underworlds client example :
        see : https://github.com/severin-lemaignan/underworlds/blob/master/clients/spatial_relations.py
        """

        bb1_min, _ = bb1
        _, bb2_max = bb2

        x1, y1, z1 = bb1_min
        x2, y2, z2 = bb2_max

        if z1 < z2 - 2 * EPSILON:
            return False

        return self.overlap(self.bb_footprint(bb1), self.bb_footprint(bb2))

    def isin(self, bb1, bb2, prev=False):
        """ Returns True if bb1 is in bb2.

        To be 'in' bb1 is weakly contained by bb2 and the bottom of bb1 is lower
        than the top of bb2 and higher than the bottom of bb2.
        Modified from severin lemaignan underworlds client example :
        see : https://github.com/severin-lemaignan/underworlds/blob/master/clients/spatial_relations.py
        """
        bb1_min, _ = bb1
        bb2_min, bb2_max = bb2

        x1, y1, z1 = bb1_min
        x2, y2, z2 = bb2_max
        x3, y3, z3 = bb2_min

        if z1 > z2 - 2 * EPSILON:
            return False

        if z1 < z3 - EPSILON:
            return False
        # else:
        #     if z1 > z2:
        #         return False
        #
        #     if z1 < z3 - EPSILON:
        #         return False

        return self.weakly_cont(self.bb_footprint(bb1), self.bb_footprint(bb2), prev)

    def isontop(self, bb1, bb2, prev=False):
        """
        For obj 1 to be on top of obj 2:
         - obj1 must be above obj 2
         - the bottom of obj 1 must be close to the top of obj 2
        Modified from severin lemaignan underworlds client example :
        see : https://github.com/severin-lemaignan/underworlds/blob/master/clients/spatial_relations.py
        """
        bb1_min, _ = bb1
        _, bb2_max = bb2

        x1, y1, z1 = bb1_min
        x2, y2, z2 = bb2_max

        return z1 < z2 + 2 * EPSILON and self.isabove(bb1, bb2)


if __name__ == '__main__':
    rospy.init_node("physics_reasoner")
    physics_reasoner = PhysicsReasoner()
    rospy.spin()
