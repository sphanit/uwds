#ifndef NODES_HPP
#define NODES_HPP

#include<string>
#include<array>
#include<map>
#include<mutex>
#include <boost/uuid/uuid_io.hpp>
#include <boost/uuid/uuid_generators.hpp>

#include "concurrent_container.h"
#include <uwds_msgs/Node.h>

using namespace std;
using namespace std_msgs;
using namespace uwds_msgs;

using namespace uwds_msgs;

namespace uwds {

  #define NEW_UUID boost::uuids::to_string(boost::uuids::random_generator()())

  /** @brief
   * The node types enum
   */
  enum NodeType {
    ENTITY = Node::ENTITY,
    MESH = Node::MESH,
    CAMERA = Node::CAMERA
  };
  /** @brief
   * The types names corresponding
   */
  static const array<string,3> NodeTypeName{"entity", "mesh", "camera"};

  /** @brief
   * This class represent the Underworlds nodes container
   */
  class Nodes : public ConcurrentContainer<Node> {

    using ConcurrentContainer::update;

    public:
      /** @brief
       * This method update a node (or create one if new)
       *
       * @param node The node to update
       */
      void update(const NodePtr node) {
        update(node->id, node);
      }

      /** @brief
       * This method update a node (or create one if new)
       *
       * @param node The node to update
       */
      void update(const Node node) {
        update(node.id, node);
      }

      /** @brief
       * This method update a set of nodes (or create them if new)
       *
       * @param nodes The nodes to update
       */
      void update(const vector<Node> nodes)
      {
        for(const auto& node : nodes)
        {
          update(node);
        }
      }

      /** @brief
       * This method update a node (or create one if new)
       *
       * @param nodes The nodes to update
       */
      void update(const vector<NodePtr> nodes)
      {
        for(const auto& node : nodes)
        {
          update(node);
        }
      }

      string getNodeProperty(const string& node_id, const string& property_name)
      {
        this->lock();
        for(const auto& property : (*this)[node_id].properties)
        {
          if (property.name == property_name)
          {
            this->unlock();
            return property.data;
          }
        }
        this->unlock();
        return "";
      }

       /** @brief
        * Returns the nodes by name
        *
        * @param property_name The property name to test
        */
       vector<NodePtr> byProperty(const string& property_name)
       {
         vector<NodePtr> nodes;
         string property;
         this->lock();
         for(const auto node : *this)
         {
           property = getNodeProperty(node->id, property_name);
           if(property != "")
             nodes.push_back(node);
         }
         this->unlock();
         return nodes;
       }

       /** @brief
        * Returns the nodes by property
        *
        * @param property_name The property name to test
        * @param property_data The property data to test
        */
       vector<NodePtr> byProperty(const string& property_name, const string& property_data)
       {
         vector<NodePtr> nodes;
         string property;
         this->lock();
         for(const auto node : *this)
         {
           property = getNodeProperty(node->id, property_name);
           if(property == property_data)
             nodes.push_back(node);
         }
         this->unlock();
         return nodes;
       }

       /** @brief
        * Returns the nodes by name
        *
        * @param name The name to test
        */
       vector<NodePtr> byName(const string& name)
       {
         vector<NodePtr> nodes;
         this->lock();
         for(const auto node : *this)
         {
           if(node->name == name)
           {
             nodes.push_back(node);
           }
         }
         this->unlock();
         return nodes;
       }

       /** @brief
        * Returns the nodes by type
        *
        * @param type The type to test
        */
       vector<NodePtr> byType(const NodeType& type)
       {
         vector<NodePtr> nodes;
         this->lock();
         for(const auto& node : *this)
         {
           if(node->type == type)
           {
             nodes.push_back(node);
           }
         }
         this->unlock();
         return nodes;
       }
  };

  typedef uwds::Nodes Nodes;
  typedef boost::shared_ptr<uwds::Nodes> NodesPtr;
  typedef boost::shared_ptr<uwds::Nodes const> NodesConstPtr;
}

#endif
