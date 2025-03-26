# get rid of old stuff
docker rmi -f $(docker images | grep "^<none>" | awk "{print $3}")
docker rm $(docker ps -q -f status=exited)

docker build --platform linux/amd64 -f Dockerfile -t maayanlab/hype:1.43 .

docker push maayanlab/hype:1.43
#docker run -p 5557:5557 -it maayanlab/hype:1.11

#docker run -v /Users/maayanlab/Documents/GitHub/hypothesispage/:/hype -p 5557:5557 -e ENDPOINT=hype -it maayanlab/hype:1.4
