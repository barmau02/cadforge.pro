import { useEffect, useRef, useState } from "react";

import * as THREE from "three";

import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

import { GCodeLoader } from "three/examples/jsm/loaders/GCodeLoader.js";



export function GcodeViewer({ gcodeUrl }: { gcodeUrl: string | null }) {

  const mountRef = useRef<HTMLDivElement>(null);

  const [error, setError] = useState<string | null>(null);

  const [loading, setLoading] = useState(false);



  useEffect(() => {

    const mount = mountRef.current;

    if (!mount || !gcodeUrl) return;



    setError(null);

    setLoading(true);



    const scene = new THREE.Scene();

    scene.background = new THREE.Color(0x0a0a0a);



    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 10000);

    const renderer = new THREE.WebGLRenderer({ antialias: true });

    renderer.setPixelRatio(window.devicePixelRatio);

    mount.appendChild(renderer.domElement);



    const controls = new OrbitControls(camera, renderer.domElement);

    controls.enableDamping = true;

    controls.dampingFactor = 0.08;



    scene.add(new THREE.AmbientLight(0xffffff, 0.55));

    const key = new THREE.DirectionalLight(0xffffff, 0.8);

    key.position.set(1, 1.5, 1);

    scene.add(key);



    const group = new THREE.Group();

    scene.add(group);

    let grid: THREE.GridHelper | null = null;

    let disposed = false;



    const resize = () => {

      const { clientWidth: w, clientHeight: h } = mount;

      if (!w || !h) return false;

      camera.aspect = w / h;

      camera.updateProjectionMatrix();

      renderer.setSize(w, h);

      return true;

    };



    const ro = new ResizeObserver(() => {

      resize();

    });

    ro.observe(mount);



    const loader = new GCodeLoader();

    loader.splitLayer = true;

    loader.load(

      gcodeUrl,

      (object) => {

        if (disposed) return;



        let lineCount = 0;

        object.traverse((child) => {

          if (child instanceof THREE.LineSegments) {

            lineCount += 1;

            if (child.material instanceof THREE.LineBasicMaterial) {

              child.material.transparent = true;

              child.material.opacity = 0.92;

            }

          }

        });



        if (lineCount === 0) {

          setLoading(false);

          setError("No toolpaths found in slice file.");

          return;

        }



        group.add(object);



        const box = new THREE.Box3().setFromObject(object);

        const size = box.getSize(new THREE.Vector3());

        const center = box.getCenter(new THREE.Vector3());

        const radius = Math.max(size.x, size.y, size.z, 1);



        object.position.sub(center);

        grid = new THREE.GridHelper(radius * 2.5, 24, 0x333333, 0x1d1d1d);

        grid.position.y = box.min.y - center.y;

        scene.add(grid);



        camera.position.set(radius * 1.4, radius * 1.1, radius * 1.5);

        camera.near = radius / 200;

        camera.far = radius * 50;

        camera.updateProjectionMatrix();

        controls.target.set(0, 0, 0);

        controls.update();



        requestAnimationFrame(() => {

          if (!disposed) resize();

        });

        setLoading(false);

      },

      undefined,

      () => {

        if (!disposed) {

          setLoading(false);

          setError("Could not load G-code toolpaths.");

        }

      },

    );



    let raf = 0;

    const animate = () => {

      raf = requestAnimationFrame(animate);

      controls.update();

      renderer.render(scene, camera);

    };

    animate();



    return () => {

      disposed = true;

      cancelAnimationFrame(raf);

      ro.disconnect();

      controls.dispose();

      group.traverse((child) => {

        if (child instanceof THREE.LineSegments) {

          child.geometry.dispose();

          (child.material as THREE.Material).dispose();

        }

      });

      grid?.dispose();

      renderer.dispose();

      mount.removeChild(renderer.domElement);

    };

  }, [gcodeUrl]);



  if (!gcodeUrl) {

    return (

      <div className="preview-empty">

        <p>Slice the model to preview toolpaths here</p>

      </div>

    );

  }



  if (error) {

    return (

      <div className="preview-empty">

        <p>{error}</p>

      </div>

    );

  }



  return (

    <div className="model-viewer gcode-viewer" ref={mountRef}>

      {loading && <div className="model-viewer-loading">Loading toolpaths…</div>}

    </div>

  );

}


