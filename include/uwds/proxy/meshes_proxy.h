#ifndef MESHES_PROXY_HPP
#define MESHES_PROXY_HPP

#include<vector>
#include<map>
#include<mutex>
#include "proxy.h"
#include "uwds_msgs/GetMesh.h"
#include "uwds/types/meshes.h"

using namespace std;
using namespace uwds_msgs;

namespace uwds {

  class PushMeshProxy : public ServiceProxy<PushMesh, Mesh>
  {
  public:
    PushMeshProxy(NodeHandlePtr nh, NodeHandlePtr pnh, ClientPtr client):ServiceProxy<PushMesh, Mesh>(nh, pnh, client, "uwds/push_mesh") {}
  protected:
    PushMesh fillRequest(Mesh mesh)
    {
      PushMesh push_mesh_srv;
      push_mesh_srv.request.mesh = mesh;
      return push_mesh_srv;
    }
  };

  typedef boost::shared_ptr<PushMeshProxy> PushMeshProxyPtr;
  typedef boost::shared_ptr<PushMeshProxy const> PushMeshProxyConstPtr;

  class GetMeshProxy : public DataProxy<Meshes, GetMesh, bool, string>
  {
  public:
    GetMeshProxy(NodeHandlePtr nh, NodeHandlePtr pnh, ClientPtr client, MeshesPtr meshes):DataProxy<Meshes, GetMesh, bool, string>(nh, pnh, client, "uwds/get_mesh", meshes) {}

    ~GetMeshProxy() {}

    virtual bool saveDataFromRemote(const GetMesh& get_mesh_srv)
    {
      if (get_mesh_srv.response.success)
      {
        this->data().update(get_mesh_srv.response.mesh);
        return true;
      }
      return false;
    }
  protected:
    virtual GetMesh fillRequest(string mesh_id)
    {
      GetMesh get_mesh_srv;
      get_mesh_srv.request.mesh_id = mesh_id;
      return get_mesh_srv;
    }
  };

  typedef boost::shared_ptr<GetMeshProxy> GetMeshProxyPtr;
  typedef boost::shared_ptr<GetMeshProxy const> GetMeshProxyConstPtr;

  class MeshesProxy
  {
  public:
    MeshesProxy(NodeHandlePtr nh, NodeHandlePtr pnh, ClientPtr client)
    {
      meshes_ = boost::make_shared<Meshes>();
      push_mesh_proxy_ = boost::make_shared<PushMeshProxy>(nh, pnh, client);
      get_mesh_proxy_ = boost::make_shared<GetMeshProxy>(nh, pnh, client, meshes_);
    }

    virtual bool pushMeshToRemote(Mesh mesh)
    {
      try {
      PushMesh push_mesh_srv = push_mesh_proxy_->call(mesh);
      return push_mesh_srv.response.success;
    } catch (std::exception e)
    {
      ROS_ERROR("Exception occured when pushing mesh <%s>: %s", mesh.id.c_str(), e.what());
    }

    }

    Mesh& operator[](const string& id)
    {
      if(meshes_->has(id)) {
        return (*meshes_)[id];
      } else {
        getMeshFromRemote(id);
        return (*meshes_)[id];
      }
    }

    bool has(string id)
    {
      return meshes_->has(id);
    }

    void update(Mesh mesh)
    {
      meshes_->update(mesh);
    }

    vector<string> update(const vector<Mesh> meshes)
    {
      return meshes_->update(meshes);
    }

    void remove(string mesh_id)
    {
      meshes_->remove(mesh_id);
    }

    void remove(vector<string> mesh_ids)
    {
      meshes_->remove(mesh_ids);
    }

    virtual bool getMeshFromRemote(string mesh_id) {return get_mesh_proxy_->getDataFromRemote(mesh_id);}

    Meshes& meshes() {return *meshes_;}

  protected:
    MeshesPtr meshes_;
    boost::shared_ptr<PushMeshProxy> push_mesh_proxy_;
    boost::shared_ptr<GetMeshProxy> get_mesh_proxy_;
  };

  typedef boost::shared_ptr<MeshesProxy> MeshesProxyPtr;
  typedef boost::shared_ptr<MeshesProxy const> MeshesProxyConstPtr;

}

#endif
